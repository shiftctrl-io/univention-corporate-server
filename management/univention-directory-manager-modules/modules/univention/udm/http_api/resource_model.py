from __future__ import absolute_import, unicode_literals
import sys
import logging
import datetime
from collections import OrderedDict
from six import string_types
from flask import g
from flask_restplus import fields
from ..udm import UDM
from ..modules.generic import GenericObject, GenericObjectProperties
from ..encoders import _classify_name, DnPropertyEncoder
from ..exceptions import NoObject, NoSuperordinate, UnknownModuleType
from .utils import resource_name2endpoint, udm_module_name2endpoint

try:
	from typing import Any, Dict, List, Optional, Text, TypeVar, Union
	import univention.admin.uldap
	from ..modules.generic import GenericModuleTV, GenericObjectTV
	from ..encoders import BaseEncoderTV
	from ..binary_props import Base64BinaryProperty
	from flask_restplus import Api, Namespace

	Obj2UrlFieldTV = TypeVar('Obj2UrlFieldTV', bound='univention.udm.http.resource_model.Obj2UrlField')
except ImportError:
	pass


logger = logging.getLogger(__name__)

#
# TODO:
# * support file uploads/downloads instead of base64 blobs
#


def get_udm_module(module_name, udm_api_version):  # type: (Text, int) -> GenericModuleTV
	udm = UDM.admin().version(udm_api_version)
	return udm.get(module_name)


class NoneList(fields.List):
	def __init__(self, cls_or_instance, **kwargs):
		self.empty_as_list = kwargs.pop('empty_as_list', False)
		super(NoneList, self).__init__(cls_or_instance, **kwargs)

	def format(self, value):  # type: (Union[Text, List[Any], None]) -> Union[List[Any], None]
		if value in ('', [], None):
			return [] if self.empty_as_list else None
		return super(NoneList, self).format(value)

	def output(self, key, data, ordered=False, **kwargs):
		# handle empty lists encoded as an empty strings which lead to
		# AttributeErrors, when flask_restplus tries to serialize them
		# happens for example with sambaLogonHours
		if hasattr(data, key) and getattr(data, key) == '':
			setattr(data, key, [])
		return super(NoneList, self).output(key, data, ordered, **kwargs)


class NoneListWithObjs(NoneList):
	def output(self, key, data, ordered=False, **kwargs):
		if (
				(isinstance(data, GenericObject) or isinstance(data, GenericObjectProperties)) and
				hasattr(data, key) and
				hasattr(getattr(data, key), 'objs')
		):
			setattr(data, key, getattr(getattr(data, key), 'objs'))
		return super(NoneListWithObjs, self).output(key, data, ordered, **kwargs)


class NoneString(fields.String):
	def format(self, value):  # type: (Optional[Text]) -> Union[Text, None]
		return None if value in ('', None) else super(NoneString, self).format(value)


class Base64BinaryProperty2StringOrNone(fields.String):
	def format(self, value):  # type: (Union[Base64BinaryProperty, Text]) -> Union[Text, None]
		return None if value in ('', None) else super(Base64BinaryProperty2StringOrNone, self).format(value.encoded)


class NoneDateField(fields.Date):
	def format(self, value):  # type: (Optional[Text]) -> Union[Text, None]
		return None if value in ('', None) else super(NoneDateField, self).format(value)


class NoneIntField(fields.Integer):
	def format(self, value):  # type: (Union[Text, int, None]) -> Union[int, None]
		return None if value in ('', 0, '0', None) else super(NoneIntField, self).format(int(value))


class IdField(fields.String):
	def format(self, value):  # type: (Optional[Text]) -> Union[Text, None]
		return super(IdField, self).format('' if value is None else value)


class Obj2UrlField(fields.Url):
	udm_module_name = ''
	endpoint = ''
	_specific_cls_cache = {}  # type: Dict[Text, Obj2UrlFieldTV]

	def __init__(self, endpoint=None, absolute=False, scheme=None, **kwargs):
		self.empty_as_string = kwargs.pop('empty_as_string', False)
		super(Obj2UrlField, self).__init__(endpoint, absolute, scheme, **kwargs)

	def id2uri(self, id):
		try:
			url_field = fields.Url(endpoint=self.endpoint, absolute=True)
			url_field_output = url_field.output('uri', {'id': id})
			res = super(Obj2UrlField, self).format(url_field_output)
			return res
		except Exception as exc:
			logger.exception('Obj2UrlField.id2uri() exc={}'.format(exc))
			raise

	def obj2uri(self, obj):  # type: (GenericObjectTV) -> Text
		assert isinstance(obj, GenericObject), '"obj" should be of (sub)type GenericObject, but is {!r}.'.format(type(obj))

		identifying_property = obj._udm_module.meta.identifying_property
		obj_id = getattr(obj.props, identifying_property)
		udm_module_name = obj._udm_module.name
		self.endpoint = udm_module_name2endpoint(udm_module_name)
		try:
			return self.id2uri(obj_id)
		except Exception:
			return obj

	def output(self, key, obj, **kwargs):  # type: (Text, Union[List[Text], Dict[Text, Any]], **Any) -> Text
		if key == 'uri':
			res_obj = obj
		elif hasattr(obj, '__iter__'):
			res_obj = obj[key]
		else:
			res_obj = getattr(obj, key)
		if isinstance(res_obj, DnPropertyEncoder.DnStr):
			res_obj = getattr(res_obj, 'obj')
		if res_obj in ('', None):
			return '' if self.empty_as_string else None
		return self.obj2uri(res_obj)

	def format(self, value):  # type: (Optional[Text]) -> Union[Text, None]
		return None if value in ('', None) else self.obj2uri(value)

	@classmethod
	def module_specifc_cls(cls, udm_module_name):  # type: (str) -> Obj2UrlFieldTV
		if udm_module_name not in cls._specific_cls_cache:
			cls_name = str('Obj2UrlField{}').format(_classify_name(udm_module_name))
			specific_obj2urlfield_cls = type(cls_name, (cls,), {})
			specific_obj2urlfield_cls.udm_module_name = udm_module_name
			cls._specific_cls_cache[udm_module_name] = specific_obj2urlfield_cls
		return cls._specific_cls_cache[udm_module_name]


type2field = {
	bool: fields.Boolean,
	datetime.date: NoneDateField,
	int: NoneIntField,
	str: NoneString,
	'Base64Binary': Base64BinaryProperty2StringOrNone,  # TODO: create a download URL
	'raw': fields.Raw,
}


def get_obj(mod):  # type: (GenericModuleTV) -> GenericObjectTV
	try:
		return mod.new()
	except NoSuperordinate as exc:
		pass
	logger.debug('Module %r requires a superordinate, trying to find one...', mod.name)
	try:
		sup_modules = mod._orig_udm_module.superordinate
	except AttributeError:
		logger.error('Got NoSuperordinate exception (%s), but %r has no "superordinate" attribute!', exc, mod.name)
		raise NoSuperordinate, exc, sys.exc_info()[2]
	if isinstance(sup_modules, string_types):
		sup_modules = [sup_modules]
	for sup_module in sup_modules:
		for obj in get_udm_module(module_name=sup_module, udm_api_version=0).search():
			logger.debug('Using {!r} object at {!r} as superordinate for model of {!r} object.'.format(
				sup_module, obj.dn, mod.name))
			return mod.new(obj)

	raise NoSuperordinate, exc, sys.exc_info()[2]


def get_model(module_name, udm_api_version, api):
	# type: (Text, int, Union[Api, Namespace]) -> Dict[Text, fields.Raw]
	logger.debug('get_model(module_name=%r, api=%s(%r))', module_name, api.__class__.__name__, api.name)
	# getting this now to raise NoSuperordinate early
	mod = get_udm_module(module_name=module_name, udm_api_version=udm_api_version)
	obj = get_obj(mod)
	if module_name == 'mail/folder':
		# handle Bug #48031
		identifying_udm_property = 'name'
		identifying_ldap_attribute = 'cn'
	elif module_name == 'settings/office365profile':
		# handle Bug #48032
		identifying_udm_property = 'name'
		identifying_ldap_attribute = 'office365ProfileName'
	else:
		identifying_udm_property = mod.meta.identifying_property
		identifying_ldap_attribute = mod.meta.mapping.udm2ldap[identifying_udm_property]
	props_is_multivalue = dict((k, bool(v.multivalue)) for k, v in obj._orig_udm_object.descriptions.iteritems())  # type: Dict[Text, bool]
	props = dict(
		(prop, NoneList(NoneString) if is_multivalue else NoneString)
		for prop, is_multivalue in props_is_multivalue.items()
	)  # type: Dict[Text, fields.Raw]
	encoders = mod._udm_object_class.udm_prop_class._encoders  # type: Dict[Text, BaseEncoderTV]
	for prop in props.keys():
		try:
			# logger.debug('****** encoders.get({!r})={!r}'.format(prop, encoders.get(prop)))
			encoder = encoders[prop]  # type: BaseEncoderTV
			# logger.debug('****** encoder for prop={!r} is {!r} encoder.type_hint={!r}'.format(
			# 	prop, encoder, getattr(encoder, 'type_hint')))
			if hasattr(encoder.type_hint, '__iter__'):
				# nested object or list
				prop_type, content_desc = encoder.type_hint
				# logger.debug('****** prop={!r} prop_type={!r} content_desc={!r}'.format(prop, prop_type, content_desc))
				if prop_type in (list, 'ObjList'):
					if prop_type is list:
						field_type = NoneList
					elif prop_type == 'ObjList':
						field_type = NoneListWithObjs
					# elif prop_type == 'DNs':
					# 	field_type = NoneListWithVaildDNs
					else:
						raise RuntimeError('Dont know what to do with encoder.type_hint={!r}'.format(encoder.type_hint))
					if isinstance(content_desc, dict):
						try:
							nested_structure = dict((k, type2field[v](attribute=k)) for k, v in content_desc.items())
						except KeyError:
							raise ValueError('Unknown encoder type in nested encoder: {!r}'.format(encoder.type_hint))
						else:
							field_content = fields.Nested(
								api.model('{}_{}'.format(_classify_name(mod.name), prop), nested_structure),
								skip_none=True
							)
					elif content_desc == 'obj':
						field_content = Obj2UrlField.module_specifc_cls(encoder.udm_module_name)
					else:
						field_content = type2field[content_desc]
					props[prop] = field_type(field_content)
				else:
					raise NotImplementedError('Unknown encoder type: {!r}'.format(encoder.type_hint))
			elif encoder.type_hint == 'obj':
				props[prop] = Obj2UrlField.module_specifc_cls(encoder.udm_module_name)
			else:
				props[prop] = type2field[encoder.type_hint]
			# logger.debug('****** props[{!r}]={!r}'.format(prop, props[prop]))
		except KeyError as exc:
			# logger.debug('****** KeyError prop={!r} exc={}'.format(prop, exc))
			pass
	props = OrderedDict((k, props[k]) for k in sorted(props.keys()))

	specific_obj2urlfield_cls = Obj2UrlField.module_specifc_cls('auto')

	return OrderedDict((
		('id', IdField(description='{} ({})'.format(identifying_udm_property, identifying_ldap_attribute))),
		('dn', fields.String(readOnly=True, description='DN of this object (read only)')),
		('options', fields.List(fields.String, description='List of options.')),
		('policies', NoneListWithObjs(
			specific_obj2urlfield_cls, description='List policy objects, that apply for this object.', empty_as_list=True)),
		('position', fields.String(description='DN of LDAP node below which the object is located.')),
		('props', fields.Nested(api.model('{}Properties'.format(_classify_name(mod.name)), props), skip_none=True)),
		('superordinate', Obj2UrlField(resource_name2endpoint(api.name), absolute=True, empty_as_string=True)),
		('uri', Obj2UrlField(resource_name2endpoint(api.name), absolute=True, empty_as_string=True)),  # TODO: , scheme='https'
	))

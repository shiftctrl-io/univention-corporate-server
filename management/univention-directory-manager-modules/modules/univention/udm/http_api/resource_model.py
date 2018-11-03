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
from ..encoders import _classify_name
from ..exceptions import NoObject, NoSuperordinate, UnknownModuleType
from .utils import resource_name2endpoint, udm_module_name2endpoint

try:
	from typing import Any, Dict, List, Optional, Text, Union
	import univention.admin.uldap
	from ..modules.generic import GenericModuleTV, GenericObjectTV
	from ..encoders import BaseEncoderTV
	from ..binary_props import Base64BinaryProperty
	from flask_restplus import Api, Namespace
except ImportError:
	pass


logger = logging.getLogger(__name__)

#
# TODO:
# * support file uploads/downloads instead of base64 blobs
# * URIs instead of DNs in properties etc
#


def get_udm_module(module_name, udm_api_version):  # type: (Text, int) -> GenericModuleTV
	udm = UDM.admin().version(udm_api_version)
	return udm.get(module_name)


class NoneList(fields.List):
	def format(self, value):  # type: (Union[Text, List[Any], None]) -> Union[List[Any], None]
		return None if value in ('', None, []) else super(NoneList, self).format(value)

	def output(self, key, data, ordered=False, **kwargs):
		# handle empty lists encoded as an empty strings which lead to
		# AttributeErrors, when flask_restplus tries to serialize them
		# happens for example with sambaLogonHours
		if hasattr(data, key) and getattr(data, key) == '':
			setattr(data, key, [])
		return super(NoneList, self).output(key, data, ordered, **kwargs)


class NoneListWithObjs(fields.List):
	def format(self, value):  # type: (Union[Text, List[Any], None]) -> Union[List[Any], None]
		logger.debug('NoneListWithObjs.format() value={!r}'.format(value))
		return None if value in ('', None, []) else super(NoneListWithObjs, self).format(value)

	def output(self, key, data, ordered=False, **kwargs):
		logger.debug('NoneListWithObjs.output() key={!r} data={!r} ordered={!r} kwargs={!r}'.format(
			key, data, ordered, kwargs))
		logger.debug('NoneListWithObjs.output() type(data)={!r}'.format(type(data)))
		if (
				(isinstance(data, GenericObject) or isinstance(data, GenericObjectProperties)) and
				hasattr(data, key) and
				hasattr(getattr(data, key), 'objs')
		):
			logger.debug('NoneListWithObjs.output() 1 getattr(data, key)={!r}'.format(getattr(data, key)))
			setattr(data, key, getattr(getattr(data, key), 'objs'))
			logger.debug('NoneListWithObjs.output() 2 getattr(data, key)={!r}'.format(getattr(data, key)))
		return super(NoneListWithObjs, self).output(key, data, ordered, **kwargs)


# class NoneListWithVaildDNs(fields.List):
# 	def format(self, value):  # type: (Union[Text, List[Any], None]) -> Union[List[Any], None]
# 		logger.debug('NoneListNoNoneInside.format() value={!r}'.format(value))
# 		return None if value in ('', None, []) else super(NoneListWithVaildDNs, self).format(value)
#
# 	def output(self, key, data, ordered=False, **kwargs):
# 		logger.debug('NoneListNoNoneInside.output() key={!r} data={!r} ordered={!r} kwargs={!r}'.format(
# 			key, data, ordered, kwargs))
# 		if hasattr(data, key) and getattr(data, key) == '':
# 			if isinstance(data, dict):
# 				data[key] = []
# 			else:
# 				setattr(data, key, [])
#
# 		if isinstance(data, dict):
# 			data[key] = [dn for dn in data[key] if g.udm.get('users/user')._dn_exists(dn)]
# 		else:
# 			setattr(data, key, [dn for dn in getattr(data, key) if g.udm.get('users/user')._dn_exists(dn)])
# 		return super(NoneListWithVaildDNs, self).output(key, data, ordered, **kwargs)


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


class Obj2UrlField(fields.Url):
	udm_module_name = ''
	endpoint = ''

	def id2uri(self, id):
		try:
			url_field = fields.Url(endpoint=self.endpoint, absolute=True)
			logger.debug('Obj2UrlField.id2uri() url_field={!r}'.format(url_field))
			url_field_output = url_field.output('uri', {'id': id})
			logger.debug('Obj2UrlField.id2uri() url_field_output={!r}'.format(url_field_output))
			res = super(Obj2UrlField, self).format(url_field_output)
			logger.debug('Obj2UrlField.id2uri() res={!r}'.format(res))
			return res
		except Exception as exc:
			logger.exception('Obj2UrlField.id2uri() exc={}'.format(exc))
			raise

	def dn2uri(self, dn):  # type: (Text) -> Text
		logger.debug('Obj2UrlField.dn2uri() dn={!r}'.format(dn))
		try:
			if self.udm_module_name == 'auto':
				udm_obj = g.udm.obj_by_dn(dn)  # type: GenericObjectTV
				udm_module_name = udm_obj._udm_module.name
			else:
				udm_obj = g.udm.get(self.udm_module_name).get(dn)  # type: GenericObjectTV
				udm_module_name = self.udm_module_name
		except NoObject:
			logger.error('NoObject for DN {!r} (loading for a {!r}).'.format(dn, self.udm_module_name))
			return ''
		except UnknownModuleType:
			logger.error('UnknownModuleType for DN {!r} (loading for a {!r}).'.format(dn, self.udm_module_name))
			return ''
		logger.debug('Obj2UrlField.dn2uri() obj={!r}'.format(udm_obj))
		self.endpoint = udm_module_name2endpoint(udm_module_name)
		logger.debug('Obj2UrlField.dn2uri() endpoint={!r}'.format(self.endpoint))
		try:
			url_field = fields.Url(endpoint=self.endpoint, absolute=True)
			logger.debug('Obj2UrlField.dn2uri() url_field={!r}'.format(url_field))
			url_field_output = url_field.output('uri', obj2dict(udm_obj))
			logger.debug('Obj2UrlField.dn2uri() url_field_output={!r}'.format(url_field_output))
			res = super(Obj2UrlField, self).format(url_field_output)
			logger.debug('Obj2UrlField.dn2uri() res={!r}'.format(res))
			return res
		except Exception as exc:
			logger.exception('Obj2UrlField.dn2uri() exc={}'.format(exc))
		return dn

	def obj2uri(self, obj):  # type: (GenericObjectTV) -> Text
		logger.debug('Obj2UrlField.obj2uri() obj={!r}'.format(obj))
		assert isinstance(obj, GenericObject)

		identifying_property = obj._udm_module.meta.identifying_property
		obj_id = getattr(obj.props, identifying_property)  # TODO: urlencode
		udm_module_name = obj._udm_module.name
		self.endpoint = udm_module_name2endpoint(udm_module_name)
		try:
			return self.id2uri(obj_id)
		except Exception as exc:
			return obj

	def output(self, key, obj, **kwargs):  # type: (Text, Union[List[Text], Dict[Text, Any]], **Any) -> Text
		logger.debug('Obj2UrlField.output() key={!r} obj={!r} kwargs={!r} udm_module_name={!r} type(obj)={!r}'.format(
			key, obj, kwargs, self.udm_module_name, type(obj)))

		if key == 'uri':
			res_obj = obj
		elif hasattr(obj, '__iter__'):
			res_obj = obj[key]
		else:
			res_obj = getattr(obj, key)
		logger.debug('Obj2UrlField.output() res_obj={!r} type(res_obj)={!r}'.format(res_obj, type(res_obj)))
		return self.obj2uri(res_obj)

	def format(self, value):  # type: (Optional[Text]) -> Union[Text, None]
		logger.debug('Obj2UrlField.format() value={!r} self.udm_module_name={!r} self.endpoint={!r}'.format(
			value, self.udm_module_name, self.endpoint))
		return self.obj2uri(value)


# class Dn2UrlField(fields.Url):
# 	udm_module_name = ''
# 	endpoint = ''
#
# 	def dn2uri(self, dn):  # type: (Text) -> Text
# 		logger.debug('Dn2UrlField.dn2uri() dn={!r}'.format(dn))
# 		try:
# 			if self.udm_module_name == 'auto':
# 				udm_obj = g.udm.obj_by_dn(dn)  # type: GenericObjectTV
# 				udm_module_name = udm_obj._udm_module.name
# 			else:
# 				udm_obj = g.udm.get(self.udm_module_name).get(dn)  # type: GenericObjectTV
# 				udm_module_name = self.udm_module_name
# 		except NoObject:
# 			logger.error('NoObject for DN {!r} (loading for a {!r}).'.format(dn, self.udm_module_name))
# 			return ''
# 		except UnknownModuleType:
# 			logger.error('UnknownModuleType for DN {!r} (loading for a {!r}).'.format(dn, self.udm_module_name))
# 			return ''
# 		logger.debug('Dn2UrlField.dn2uri() obj={!r}'.format(udm_obj))
# 		self.endpoint = udm_module_name2endpoint(udm_module_name)
# 		logger.debug('Dn2UrlField.dn2uri() endpoint={!r}'.format(self.endpoint))
# 		try:
# 			url_field = fields.Url(endpoint=self.endpoint, absolute=True)
# 			logger.debug('Dn2UrlField.dn2uri() url_field={!r}'.format(url_field))
# 			url_field_output = url_field.output('uri', obj2dict(udm_obj))
# 			logger.debug('Dn2UrlField.dn2uri() url_field_output={!r}'.format(url_field_output))
# 			res = super(Dn2UrlField, self).format(url_field_output)
# 			logger.debug('Dn2UrlField.dn2uri() res={!r}'.format(res))
# 			return res
# 		except Exception as exc:
# 			logger.exception('Dn2UrlField.dn2uri() exc={}'.format(exc))
# 		return dn
#
# 	def output(self, key, obj, **kwargs):  # type: (Text, Union[List[Text], Dict[Text, Any]], **Any) -> Text
# 		logger.debug('Dn2UrlField.output() key={!r} obj={!r} kwargs={!r} udm_module_name={!r}'.format(
# 			key, obj, kwargs, self.udm_module_name))
#
# 		dn = obj[key]
# 		logger.debug('Dn2UrlField.output() dn={!r}'.format(dn))
# 		return self.dn2uri(dn)
#
# 	def format(self, value):  # type: (Optional[Text]) -> Union[Text, None]
# 		logger.debug('Dn2UrlField.format() value={!r} self.udm_module_name={!r} self.endpoint={!r}'.format(
# 			value, self.udm_module_name, self.endpoint))
# 		return self.dn2uri(value)


type2field = {
	bool: fields.Boolean,
	datetime.date: NoneDateField,
	int: NoneIntField,
	str: NoneString,
	'Base64Binary': Base64BinaryProperty2StringOrNone,  # TODO: create a download URL
	'raw': fields.Raw,
}


def obj2dict(obj):  # type: (GenericObjectTV) -> Dict[Text, Any]
	identifying_property = obj._udm_module.meta.identifying_property
	return {
		'id': getattr(obj.props, identifying_property),  # TODO: urlencode
		'dn': obj.dn,
		'options': obj.options,
		'policies': obj.policies,
		'position': obj.position,
		'props': obj.props,
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
			return mod.new(obj.dn)  # TODO: fix in upstream

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
		identifying_ldap_attribute = mod.meta.mapping.udm2ldap[identifying_udm_property]  # TODO: urlencode
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
					# elif content_desc == 'DN':
					# 	cls_name = str('Dn2UrlField{}').format(_classify_name(encoder.udm_module_name))
					# 	specific_dn2urlfield_cls = type(cls_name, (Dn2UrlField,), {})
					# 	specific_dn2urlfield_cls.udm_module_name = encoder.udm_module_name
					# 	field_content = specific_dn2urlfield_cls
					elif content_desc == 'obj':
						cls_name = str('Obj2UrlField{}').format(_classify_name(encoder.udm_module_name))
						specific_obj2urlfield_cls = type(cls_name, (Obj2UrlField,), {})
						specific_obj2urlfield_cls.udm_module_name = encoder.udm_module_name
						field_content = specific_obj2urlfield_cls
					else:
						field_content = type2field[content_desc]
					props[prop] = field_type(field_content)
				else:
					raise NotImplementedError('Unknown encoder type: {!r}'.format(encoder.type_hint))
			else:
				props[prop] = type2field[encoder.type_hint]
			# logger.debug('****** props[{!r}]={!r}'.format(prop, props[prop]))
		except KeyError as exc:
			# logger.debug('****** KeyError prop={!r} exc={}'.format(prop, exc))
			pass
	props = OrderedDict((k, props[k]) for k in sorted(props.keys()))

	cls_name = str('Obj2UrlField{}').format('Auto')
	specific_obj2urlfield_cls = type(cls_name, (Obj2UrlField,), {})
	specific_obj2urlfield_cls.udm_module_name = 'auto'

	return OrderedDict((
		('id', fields.String(description='{} ({})'.format(identifying_udm_property, identifying_ldap_attribute))),
		('dn', fields.String(readOnly=True, description='DN of this object (read only)')),
		('options', fields.List(fields.String, description='List of options.')),
		('policies', NoneListWithObjs(
			specific_obj2urlfield_cls, description='List policy objects, that apply for this object.')),
		('position', fields.String(description='DN of LDAP node below which the object is located.')),
		('props', fields.Nested(api.model('{}Properties'.format(_classify_name(mod.name)), props), skip_none=True)),
		('uri', Obj2UrlField(resource_name2endpoint(api.name), absolute=True)),  # TODO: , scheme='https'
	))

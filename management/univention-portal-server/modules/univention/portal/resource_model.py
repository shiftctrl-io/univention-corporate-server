from __future__ import absolute_import, unicode_literals
import sys
import logging
from collections import OrderedDict
from six import string_types
from flask_restplus import fields
from univention.udm import UDM
from univention.udm.modules.generic import GenericObject, GenericObjectProperties
from univention.udm.encoders import _classify_name, DnPropertyEncoder
from univention.udm.exceptions import NoSuperordinate
from univention.udm.http_api.utils import get_identifying_property, udm_module_name2endpoint

try:
	from typing import Any, Dict, List, Optional, Text, TypeVar, Union
	import univention.admin.uldap
	from univention.udm.modules.generic import GenericModuleTV, GenericObjectTV
	from univention.udm.encoders import BaseEncoderTV
	from univention.udm.binary_props import Base64BinaryProperty
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


class Base64BinaryProperty2StringOrNone(fields.String):
	def format(self, value):  # type: (Union[Base64BinaryProperty, Text]) -> Union[Text, None]
		return None if value in ('', None) else super(Base64BinaryProperty2StringOrNone, self).format(value.encoded)


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

		_idl, identifying_property = get_identifying_property(obj._udm_module)
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


def get_base_model(api):  # type: (Union[Api, Namespace]) -> Dict[Text, fields.Raw]
	logger.debug('get_base_model()')

	return api.model('base', OrderedDict((
		('id', IdField(description='ID of this object.')),
		('dn', fields.String(readOnly=True, description='DN of this object (read only)')),
	)))


def get_specific_model(module_name, udm_api_version, api):
	# type: (Text, int, Union[Api, Namespace]) -> Dict[Text, fields.Raw]
	logger.debug('get_specific_model(%r)', module_name)
	# mod = get_udm_module(module_name=module_name, udm_api_version=udm_api_version)
	# obj = get_obj(mod)
	props = {}
	if module_name == 'settings/portal':
		props = {
			"showMenu": fields.String,
			"showApps": fields.String,
			"displayName": fields.Raw,
			"displayName_l10n": fields.String,
			"name": fields.String,
			"links": fields.List(fields.String),
			"portalEntriesOrder": fields.List(fields.String),
			"content": fields.String,
			"showServers": fields.String,
			"showLogin": fields.String,
			"cssBackground": fields.String,
			"background": fields.String,
			"portalComputers": fields.List(fields.String),
			"logo": fields.String,
			"showSearch": fields.String,
			"fontColor": fields.String
		}
	elif module_name == 'settings/portal_category':
		props = {
			"displayName": fields.Raw,
			"displayName_l10n": fields.String,
			"name": fields.String
		}
	elif module_name == 'settings/portal_entry':
		props = {
			"category": fields.String,
			"displayName": fields.Raw,
			"displayName_l10n": fields.String,
			"description": fields.Raw,
			"description_l10n": fields.String,
			"name": fields.String,
			"favorite": fields.String,
			"activated": fields.String,
			"allowedGroups": fields.List(fields.String),
			"authRestriction": fields.String,
			"link": fields.List(fields.String),
			"portal": fields.List(fields.String),
			"icon": fields.String
		}

	props = OrderedDict((k, props[k]) for k in sorted(props.keys()))

	return OrderedDict((
		('props', fields.Nested(api.model('{}Properties'.format(_classify_name(module_name)), props), skip_none=True)),
		('uri', Obj2UrlField(udm_module_name2endpoint(module_name), absolute=True, empty_as_string=True)), # TODO: , scheme='https'
	))

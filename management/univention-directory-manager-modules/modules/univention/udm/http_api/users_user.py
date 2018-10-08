from __future__ import absolute_import, unicode_literals
import logging
import datetime
from collections import OrderedDict
from flask_restplus import fields
from ..udm import Udm
from ..encoders import _classify_name

try:
	from typing import Dict, Optional, Text
	import univention.admin.uldap
	from ..base import BaseUdmModule
	from ..binary_props import Base64BinaryProperty
	from ..encoders import BaseEncoder
	from flask_restplus import Api
except ImportError:
	pass


class NoneList(fields.List):
	def format(self, value):
		logger.debug('value=%r', value)
		return value if value else None


class NoneString(fields.String):
	def format(self, value):
		logger.debug('value=%r', value)
		return value if value not in ('', None) else None


class Base64BinaryProperty2String(fields.Raw):
	def format(self, value):  # type: (Base64BinaryProperty) -> Text
		assert isinstance(value, Base64BinaryProperty)
		return value.encoded


type2field = {
	bool: fields.Boolean,
	datetime.date: fields.Date,
	int: fields.Integer,
	str: NoneString,
	'Base64Binary': Base64BinaryProperty2String,
}


logger = logging.getLogger(__name__)


def get_module(module_name, lo=None):  # type: (Text, Optional[univention.admin.uldap.access]) -> BaseUdmModule
	logger.debug('get_module(module_name={!r}, lo={!r})'.format(module_name, lo))
	if lo:
		udm = Udm(lo, 1)
	else:
		udm = Udm.using_admin(1)
	return udm.get(module_name)


def get_model(module_name, api, lo=None):
	# type: (Text, Api, Optional[univention.admin.uldap.access]) -> Dict[Text, fields.Raw]
	logger.debug('get_model(module_name={!r}, api={!r} lo={!r})'.format(module_name, api, lo))
	mod = get_module(module_name=module_name, lo=lo)
	obj = mod.new()
	logger.debug('get_model({!r}) obj={!r}'.format(lo, obj))
	identifying_udm_property = mod.meta.identifying_property
	identifying_ldap_attribute = mod.meta.mapping.udm2ldap[identifying_udm_property]
	res = OrderedDict((
		('id', fields.String(description='{} ({})'.format(identifying_udm_property, identifying_ldap_attribute))),
		('dn', fields.String(readOnly=True, description='DN of this object (read only)')),
		('options', fields.List(fields.String, description='List of options.')),
		('policies', fields.List(fields.String, description='List of DNs to policy objects, that apply for this object.')),
		('position', fields.String(description='DN of LDAP node below which the object is located.')),
	))  # type: Dict[Text, fields.Raw]
	props_is_multivalue = dict((k, bool(v.multivalue)) for k, v in obj._udm1_object.descriptions.iteritems())  # type: Dict[Text, bool]
	props = dict(
		(prop, NoneList(NoneString) if is_multivalue else NoneString)
		for prop, is_multivalue in props_is_multivalue.items()
	)  # type: Dict[Text, fields.Raw]
	encoders = mod._udm_object_class.udm_prop_class._encoders  # type: Dict[Text, BaseEncoder]
	# logger.debug('** props={!r}'.format(props))
	# logger.debug('** encoders={!r}'.format(encoders))
	for prop in props.keys():
		logger.debug('prop=%r', prop)
		try:
			encoder = encoders[prop]
			logger.debug('encoder=%r', encoder)
			# logger.debug('** prop={!r} encoder={!r}'.format(prop, encoder))
			if hasattr(encoder.type, '__iter__'):
				logger.debug('hasiter')
				# nested object or list
				prop_type, content_desc = encoder.type
				logger.debug('prop_type=%r content_desc=%r', prop_type, content_desc)
				if prop_type is dict:
					field_type = fields.Nested
					field_kwargs = {'skip_none': True}
					try:
						nested_structure = dict((k, type2field[v]) for k, v in content_desc.items())
					except KeyError:
						raise ValueError('Unknown encoder type in nested encoder: {!r}'.format(encoder.type))
					else:
						field_content = api.model('{}Prop_{}'.format(_classify_name(mod.name), prop), nested_structure)
				elif prop_type is list:
					field_type = NoneList
					field_kwargs = {}
					if isinstance(content_desc, dict):
						try:
							nested_structure = dict((k, type2field[v]) for k, v in content_desc.items())
							logger.debug('nested_structure=%r', nested_structure)
						except KeyError:
							raise ValueError('Unknown encoder type in nested encoder: {!r}'.format(encoder.type))
						else:
							field_content = fields.Nested(
								api.model('{}Prop_{}'.format(_classify_name(mod.name), prop), nested_structure),
								skip_none=True
							)
							logger.debug('field_content=%r', field_content)
					else:
						field_content = type2field[content_desc]
				else:
					raise ValueError('Unknown encoder type: {!r}'.format(encoder.type))
				logger.debug('props[{!r}] = {!r}({!r}, **{!r})'.format(prop, field_type, field_content, field_kwargs))
				props[prop] = field_type(field_content, **field_kwargs)
			else:
				logger.debug('encoder.type=%r', encoder.type)
				props[prop] = type2field[encoder.type]
				logger.debug('props[prop]=%r', props[prop])
			# logger.debug('** props[{!r}]={!r}'.format(prop, props[prop]))
		except KeyError:
			pass
	props = OrderedDict((k, props[k]) for k in sorted(props.keys()))
	logger.debug('props=%r', props)
	res['props'] = fields.Nested(api.model('{}Props'.format(_classify_name(mod.name)), props), skip_none=True)
	res['uri'] = fields.Url('{}_{}'.format(mod.name, '_'.join(mod.name.split('/'))))
	logger.debug('res={!r}'.format(res))
	return res

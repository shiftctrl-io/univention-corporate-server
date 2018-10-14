from __future__ import absolute_import, unicode_literals
import logging
import datetime
from collections import OrderedDict
from flask_restplus import fields
from ..udm import Udm
from ..encoders import _classify_name

try:
	from typing import Dict, Optional, Text, Union
	import univention.admin.uldap
	from ..base import BaseUdmModule
	from ..encoders import BaseEncoder
	from ..binary_props import Base64BinaryProperty
	from flask_restplus import Api
except ImportError:
	pass


UDM_API_VERSION = 1


class NoneList(fields.List):
	def format(self, value):
		return None if value in ('', None, []) else super(NoneList, self).format(value)

	def output(self, key, data, ordered=False, **kwargs):
		# handle empty lists encoded as an empty strings which lead to
		# AttributeErrors, when flask_restplus tries to serialize them
		# happens for example with sambaLogonHours
		if hasattr(data, key) and getattr(data, key) == '':
			setattr(data, key, [])
		return super(NoneList, self).output(key, data, ordered, **kwargs)


class NoneString(fields.String):
	def format(self, value):
		return None if value in ('', None) else super(NoneString, self).format(value)


class Base64BinaryProperty2StringOrNone(fields.Raw):
	def format(self, value):  # type: (Union[Base64BinaryProperty, Text]) -> Union[Text, None]
		return None if value in ('', None) else super(Base64BinaryProperty2StringOrNone, self).format(value.encoded)


class NoneDateField(fields.Date):
	def format(self, value):
		return None if value in ('', None) else super(NoneDateField, self).format(value)


type2field = {
	bool: fields.Boolean,
	datetime.date: NoneDateField,
	int: fields.Integer,
	str: NoneString,
	'Base64Binary': Base64BinaryProperty2StringOrNone,
}


logger = logging.getLogger(__name__)


def get_module(module_name, lo=None):  # type: (Text, Optional[univention.admin.uldap.access]) -> BaseUdmModule
	if lo:
		udm = Udm(lo, UDM_API_VERSION)
	else:
		udm = Udm.using_admin().version(UDM_API_VERSION)
	return udm.get(module_name)


def get_model(module_name, api, lo=None):
	# type: (Text, Api, Optional[univention.admin.uldap.access]) -> Dict[Text, fields.Raw]
	logger.debug('get_model(module_name=%r, api=%s(%r) lo=%r)', module_name, api.__class__.__name__, api.name, lo)
	mod = get_module(module_name=module_name, lo=lo)
	obj = mod.new()
	identifying_udm_property = mod.meta.identifying_property
	identifying_ldap_attribute = mod.meta.mapping.udm2ldap[identifying_udm_property]
	props_is_multivalue = dict((k, bool(v.multivalue)) for k, v in obj._udm1_object.descriptions.iteritems())  # type: Dict[Text, bool]
	props = dict(
		(prop, NoneList(NoneString) if is_multivalue else NoneString)
		for prop, is_multivalue in props_is_multivalue.items()
	)  # type: Dict[Text, fields.Raw]
	encoders = mod._udm_object_class.udm_prop_class._encoders  # type: Dict[Text, BaseEncoder]
	for prop in props.keys():
		try:
			encoder = encoders[prop]
			if hasattr(encoder.type, '__iter__'):
				# nested object or list
				prop_type, content_desc = encoder.type
				if prop_type is list:
					field_type = NoneList
					if isinstance(content_desc, dict):
						try:
							nested_structure = dict((k, type2field[v](attribute=k)) for k, v in content_desc.items())
						except KeyError:
							raise ValueError('Unknown encoder type in nested encoder: {!r}'.format(encoder.type))
						else:
							field_content = fields.Nested(
								api.model('{}_{}'.format(_classify_name(mod.name), prop), nested_structure),
								skip_none=True
							)
					else:
						field_content = type2field[content_desc]
				else:
					raise NotImplementedError('Unknown encoder type: {!r}'.format(encoder.type))
				props[prop] = field_type(field_content)
			else:
				props[prop] = type2field[encoder.type]
		except KeyError:
			pass
	props = OrderedDict((k, props[k]) for k in sorted(props.keys()))
	return OrderedDict((
		('id', fields.String(description='{} ({})'.format(identifying_udm_property, identifying_ldap_attribute))),
		('dn', fields.String(readOnly=True, description='DN of this object (read only)')),
		('options', fields.List(fields.String, description='List of options.')),
		('policies', fields.List(fields.String, description='List of DNs to policy objects, that apply for this object.')),
		('position', fields.String(description='DN of LDAP node below which the object is located.')),
		('props', fields.Nested(api.model('{}Props'.format(_classify_name(mod.name)), props), skip_none=True)),
		('uri', fields.Url('api.{}_{}'.format(api.name, '_'.join(mod.name.split('/'))), absolute=True)),
	))

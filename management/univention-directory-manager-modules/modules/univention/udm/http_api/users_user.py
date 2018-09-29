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
	from ..encoders import BaseEncoder
	from flask_restplus import Api
except ImportError:
	pass


class NoneString(fields.String):
	def format(self, value):
		return value if value else None


type2field = {
	bool: fields.Boolean,
	datetime.date: fields.Date,
	int: fields.Integer,
	str: NoneString,
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
	props_is_multivalue = dict((k, bool(v.multivalue)) for k, v in obj._udm1_object.descriptions.iteritems())  # type: Dict[Text, bool]
	res = OrderedDict((
		('id', fields.String(description='{} ({})'.format(identifying_udm_property, identifying_ldap_attribute))),
		('dn', fields.String(readOnly=True, description='DN of this object (read only)')),
		('options', fields.List(fields.String, description='List of options.')),
		('policies', fields.List(fields.String, description='List of DNs to policy objects, that apply for this object.')),
		('position', fields.String(description='DN of LDAP node below which the object is located.')),
	))  # type: Dict[Text, fields.Raw]
	props = dict(
		(prop, fields.List(NoneString) if is_multivalue else NoneString)
		for prop, is_multivalue in props_is_multivalue.items()
	)  # type: Dict[Text, fields.Raw]
	encoders = mod._udm_object_class.udm_prop_class._encoders  # type: Dict[Text, BaseEncoder]
	# logger.debug('** props={!r}'.format(props))
	# logger.debug('** encoders={!r}'.format(encoders))
	for prop in props.keys():
		try:
			encoder = encoders[prop]
			# logger.debug('** prop={!r} encoder={!r}'.format(prop, encoder))
			if hasattr(encoder.type, '__iter__'):
				# nested object or list
				prop_type, content_desc = encoder.type
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
					field_type = fields.List
					field_kwargs = {}
					field_content = type2field[content_desc]
				else:
					raise ValueError('Unknown encoder type: {!r}'.format(encoder.type))
				# logger.debug('props[{!r}] = {!r}({!r})'.format(prop, field_type, field_content))
				props[prop] = field_type(field_content, **field_kwargs)
			else:
				props[prop] = type2field[encoder.type]
			# logger.debug('** props[{!r}]={!r}'.format(prop, props[prop]))
		except KeyError:
			pass
	props = OrderedDict((k, props[k]) for k in sorted(props.keys()))
	res['props'] = fields.Nested(api.model('{}Props'.format(_classify_name(mod.name)), props), skip_none=True)
	res['uri'] = fields.Url('{}_{}'.format(mod.name, '_'.join(mod.name.split('/'))))
	logger.debug('get_model() uri={!r}'.format(res['uri']))
	# logger.debug('get_model() res={!r}'.format(res))
	return res

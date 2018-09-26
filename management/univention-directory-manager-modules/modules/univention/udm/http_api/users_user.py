from __future__ import absolute_import, unicode_literals
from flask_restplus import fields
from univention.udm import Udm

try:
	from typing import Dict, Optional, Text
	import univention.admin.uldap
	from ..base import BaseUdmModule
except ImportError:
	pass


module_name = 'users/user'


def get_module(lo=None):  # type: (Optional[univention.admin.uldap.access]) -> BaseUdmModule
	if lo:
		udm = Udm(lo, 0)
	else:
		udm = Udm.using_admin(0)
	return udm.get(module_name)


def get_model(lo=None):  # type: (Optional[univention.admin.uldap.access]) -> Dict[Text, fields.Raw]
	obj = get_module(lo).new()
	props_is_multivalue = dict((k, bool(v.multivalue)) for k, v in obj._udm1_object.descriptions.iteritems())
	res = dict(
		(prop, fields.List(fields.String) if is_multivalue else fields.String)
		for prop, is_multivalue in props_is_multivalue.iteritems()
	)
	res['dn'] = fields.String
	return res

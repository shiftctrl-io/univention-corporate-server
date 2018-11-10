from __future__ import absolute_import, unicode_literals

import re
import logging
import urllib
import urlparse
import datetime
from six import string_types
from ldap.filter import filter_format
from flask import Blueprint, Flask, g
from flask_httpauth import HTTPBasicAuth
from flask_restplus import Api, Namespace, Resource, abort, reqparse
from werkzeug.contrib.fixers import ProxyFix
from univention.admin.uexceptions import authFail, valueInvalidSyntax

from ..udm import UDM
from ..exceptions import NoSuperordinate, UdmError
from ..encoders import _classify_name
from ..helpers import get_all_udm_module_names
from .utils import setup_logging, ucr
from .resource_model import get_model

try:
	from typing import Any, Dict, List, Optional, Text, Tuple
	from ..base import BaseObjectTV
	from ..encoders import BaseEncoderTV
	from flask_restplus import Model
except ImportError:
	pass


UDM_API_VERSION = 1
HTTP_API_VERSION = '{}.0'.format(UDM_API_VERSION)

_url2module = {}  # type: Dict[Text, Text]
_uri_regex = re.compile(r'^(https{0,1}?)://(.+?)/udm/(\w+?)/(\w+?)/(.*)')

# https://swagger.io/docs/specification/2-0/authentication/
authorizations = {
	'basic': {'type': 'basic'}
}
auth = HTTPBasicAuth()

app = Flask(__name__)
setup_logging(app)
logger = logging.getLogger(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
blueprint = Blueprint('api', __name__, url_prefix='/udm')
api = Api(
	blueprint,
	version=HTTP_API_VERSION,
	title='UDM API',
	description='A simple UDM API',
	authorizations=authorizations,
	security='basic',
)
app.register_blueprint(blueprint)


def search_single_object(udm, module_name, id, abort_on_error=True):
	# type: (UDM, Text, Text, Optional[bool]) -> BaseObjectTV
	mod = udm.get(module_name)
	identifying_property = mod.meta.identifying_property

	if id in (None, '', ','):
		obj = mod.new()
		obj.id = '_new_'
		setattr(obj.props, identifying_property, '_new_')
		return obj

	filter_s = filter_format('%s=%s', (identifying_property, id))
	res = list(mod.search(filter_s))
	if len(res) == 0:
		msg = 'Object with id ({}) {!r} not found.'.format(identifying_property, id)
		logger.error('404: %s', msg)
		if abort_on_error:
			abort(404, msg)
	elif len(res) == 1:
		setattr(res[0], 'id', id)
		return res[0]
	else:
		logger.error('500: More than on %r object found, using filter %r.', module_name, filter_s)
		if abort_on_error:
			abort(500)
	return None


def docstring_params(*args, **kwargs):
	"""Decorator that formats docstrings."""
	def dec_func(obj):
		obj.__doc__ = obj.__doc__.format(*args, **kwargs)
		return obj
	return dec_func


def url2dn(udm, url):  # type: (UDM, Text) -> Text
	# url2dn - without doing a GET on the url and simply reading the DN
	path = urlparse.urlsplit(url).path
	resource_url, _sep, obj_id_enc = path.rpartition('/')
	obj_id = urllib.unquote(obj_id_enc)
	try:
		module_name = _url2module[resource_url]
	except KeyError:
		msg = 'Cannot find module to path in URL {!r}.'.format(url)
		logger.error('422: %s', msg)
		abort(422, msg)
	obj = search_single_object(udm, module_name, obj_id, abort_on_error=False)
	if not obj:
		msg = 'Cannot find {!r} object in LDAP for {!r}.'.format(module_name, url)
		logger.error('422: %s', msg)
		abort(422, msg)
	return obj.dn


@auth.verify_password
def verify_pw(username, password):  # type: (Text, Text) -> bool
	# logger.debug('*** username=%r password=%r', username, password)
	if g.get('udm'):
		logger.error('Already set: g.udm=%r', g.udm)
		abort(500)
	if not (username and password):
		return False
	try:
		g.udm = UDM.credentials(username, password).version(UDM_API_VERSION)
		return True
	except authFail:
		return False


list_filter_parser = reqparse.RequestParser()
list_filter_parser.add_argument('filter', type=str, location='headers', dest='filter_s', help='LDAP filter [optional].')
list_filter_parser.add_argument('base', type=str, location='headers', help='LDAP subtree to search [optional].')
list_filter_parser.add_argument('scope', type=str, location='headers', help='LDAP scope to apply [optional].')
modify_parser = reqparse.RequestParser()
modify_parser.add_argument('options', type=list, help='Options of object [optional].')
modify_parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
modify_parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
modify_parser.add_argument('props', type=dict, help='Properties of object [optional].')
modify_parser.add_argument('superordinate', type=str, help='Superordinate object [optional].')


def create_resource(module_name, namespace, api_model):  # type: (Text, Namespace, Model) -> Tuple[Any, Any]

	@namespace.route('/')
	@namespace.doc('{}ResourceList'.format(_classify_name(module_name)))
	class UdmResourceList(Resource):
		_udm_object_type = module_name
		method_decorators = (auth.login_required,)

		@namespace.doc('list')
		@namespace.marshal_list_with(api_model, skip_none=True)
		@api.expect(list_filter_parser)
		@docstring_params(_udm_object_type.split('/')[-1])
		def get(self):  # type: () -> Tuple[List[Dict[Text, Any]], int]
			"""List all {} objects."""
			args = list_filter_parser.parse_args()
			logger.debug('UdmResourceList.get() self._udm_object_type=%r args=%r', self._udm_object_type, args)
			search_kwargs = dict((k, v.strip()) for k, v in args.items() if v and v.strip())  # remove empty values
			mod = g.udm.get(self._udm_object_type)
			identifying_property = mod.meta.identifying_property
			res = []
			try:
				for obj in mod.search(**search_kwargs):
					setattr(obj, 'id', getattr(obj.props, identifying_property))
					res.append(obj)
			except valueInvalidSyntax:
				msg = 'The LDAP query had an invalid syntax.'
				logger.error('422: %s', msg)
				abort(422, msg)
			if not res:
				msg = 'No {!r} objects exist.'.format(self._udm_object_type)
				logger.error('404: %s', msg)
				abort(404, msg)
			return res, 200

		@namespace.doc('create')
		@namespace.expect(api_model)
		@namespace.marshal_with(api_model, skip_none=True, code=201)
		@api.expect(modify_parser)
		@docstring_params(_udm_object_type.split('/')[-1])
		def post(self):  # type: () -> Tuple[Dict[Text, Any], int]
			"""Create a new {} object."""
			logger.debug('UdmResourceList.post() self._udm_object_type=%r', self._udm_object_type)
			mod = g.udm.get(self._udm_object_type)
			identifying_property = mod.meta.identifying_property
			args = modify_parser.parse_args()
			try:
				obj_id = args['props'][mod.meta.identifying_property]
			except KeyError:
				msg = 'ID of object is required in "props.{}".'.format(identifying_property)
				logger.error('400: %s', msg)
				abort(400, msg)
			logger.info('Creating %r object with args %r...', self._udm_object_type, args)
			obj = mod.new()  # type: BaseObjectTV
			obj.options = args.get('options') or []
			obj.policies = args.get('policies') or []
			obj.position = args.get('position') or mod._get_default_object_positions()[0]
			for k, v in args['props'].items():
				setattr(obj.props, k, v)
			try:
				obj.save().reload()
			except UdmError as exc:
				logger.error('400: %s', exc)
				abort(400, str(exc))
			obj.id = obj_id
			return obj, 201

	@namespace.route('/<string:id>')
	@namespace.doc('{}Resource'.format(_classify_name(module_name)))
	@namespace.response(404, 'Object not found')
	@namespace.param('id', 'The objects ID (username, group name etc).')
	class UdmResource(Resource):
		_udm_object_type = module_name
		method_decorators = (auth.login_required,)

		@namespace.doc('get')
		@namespace.marshal_with(api_model, skip_none=True)
		@docstring_params(_udm_object_type.split('/')[-1])
		def get(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
			"""Fetch a {} object given its id."""
			logger.debug('UdmResourceList.get() id=%r self._udm_object_type=%r', id, self._udm_object_type)
			obj = search_single_object(g.udm, self._udm_object_type, id)
			return obj, 200

		@namespace.doc('delete')
		@namespace.response(204, 'Object deleted')
		@docstring_params(_udm_object_type.split('/')[-1])
		def delete(self, id):  # type: (Text) -> Tuple[Text, int]
			"""Delete a {} object given its id."""
			logger.debug('UdmResourceList.delete() id=%r self._udm_object_type=%r', id, self._udm_object_type)
			obj = search_single_object(g.udm, self._udm_object_type, id)
			logger.info('Deleting {!r}...'.format(obj))
			obj.delete()
			return '', 204

		@namespace.doc('modify')
		@namespace.expect(api_model)
		@namespace.marshal_with(api_model, skip_none=True)
		@api.expect(modify_parser)
		@docstring_params(_udm_object_type.split('/')[-1])
		def put(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
			"""Update a {} object given its id."""
			logger.debug('UdmResourceList.put(id=%r) self._udm_object_type=%r', id, self._udm_object_type)
			# TODO: superordinate
			args = modify_parser.parse_args()
			obj = search_single_object(g.udm, self._udm_object_type, id)
			logger.info('Updating %r with args %r...', obj, args)
			changed = False
			for udm_attr in ('options', 'policies', 'position'):
				if args.get(udm_attr) is not None:
					logger.debug(
						'(%s) Setting %s to %r (old_value=%r).', id, udm_attr, args[udm_attr], getattr(obj, udm_attr))
					setattr(obj, udm_attr, args[udm_attr])
					changed = True
			if obj.policies and isinstance(obj.policies, list):
				obj.policies = [
					url2dn(g.udm, url) for url in obj.policies
					if isinstance(url, string_types) and _uri_regex.match(url)
				]

			for prop, value in (args.get('props') or {}).iteritems():
				# logger.debug('*** props.%s: %r', prop, value)
				if getattr(obj.props, prop) == '' and value is None:
					# Ignore values we set to None earlier (instead of ''), so they
					# wouldn't be shown in the API.
					continue
				old_value = getattr(obj.props, prop)
				try:
					encoder = obj.props._encoders[prop]  # type: BaseEncoderTV
				except KeyError:
					pass
				else:
					# logger.debug('(%s) encoder=%r encoder.type_hint=%r', id, encoder, encoder.type_hint)
					if hasattr(encoder.type_hint, '__iter__'):
						# nested object or list
						prop_type, content_desc = encoder.type_hint
						# logger.debug(
						# 	'prop_type(%s)=%r content_desc(%s)=%r',
						# 	type(prop_type), prop_type, type(content_desc), content_desc)
						is_list = prop_type in (list, 'ObjList')
						if isinstance(content_desc, dict):
							pass
						elif content_desc == 'obj':
							# Obj2UrlField
							if is_list:
								value = [url2dn(g.udm, url) for url in value]
							else:
								value = url2dn(g.udm, value)
						else:
							pass
					elif encoder.type_hint == 'obj':
						# Obj2UrlField
						value = url2dn(g.udm, value)
					elif encoder.type_hint == datetime.date:
						value = datetime.datetime.strptime(value, '%Y-%m-%d').date()
				if old_value != value:
					logger.debug('(%s) Setting props.%s to %r (old_value=%r).', id, prop, value, old_value)
					setattr(obj.props, prop, value)
					changed = True
			if changed:
				try:
					obj.save().reload()
				except UdmError as exc:
					logger.error('400: (%s) %s', id, exc)
					abort(400, str(exc))
			else:
				logger.info('No change to %r.', obj)
			return obj, 200

	return UdmResourceList, UdmResource


incomplete_modules = (
	'dhcp/dhcp', 'dns/dns', 'mail/mail', 'oxmail/oxmail', 'policies/policy', 'settings/portal_all', 'settings/settings',
	'shares/print', 'users/passwd', 'users/self',
)
logger.info('Skipping UDM modules without mapping: %r.', incomplete_modules)

for udm_object_type in [m for m in get_all_udm_module_names() if m not in incomplete_modules]:
	# if not any(udm_object_type.startswith(x) for x in ('nagios', 'policies', 'computer', 'user', 'group', 'saml')):
	# 	logger.info('*** Skipping %r...', udm_object_type)
	# 	continue
	ns = Namespace(
		udm_object_type.replace('/', '-'),
		description='{} related operations'.format(udm_object_type)
	)
	try:
		model = get_model(module_name=udm_object_type, udm_api_version=UDM_API_VERSION, api=ns)
	except NoSuperordinate as exc:
		logger.warn(exc)
		continue
	ns_model = ns.model(udm_object_type.replace('/', '-'), model)
	api.add_namespace(ns, path='/{}'.format(udm_object_type))
	create_resource(udm_object_type, ns, ns_model)
	_url2module['{}/{}'.format(blueprint.url_prefix, api.get_ns_path(ns).strip('/'))] = udm_object_type

# TODO: ressource for metadata:
# * get supported API versions
# * credentials test


if __name__ == '__main__':
	import logging
	logger.addHandler(logging.StreamHandler())
	app.run(debug=True, host='0.0.0.0', port=int(ucr.get('directory/manager/http_api/wsgi_server/port', 8999)))

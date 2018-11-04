from __future__ import absolute_import, unicode_literals

import logging
import urllib
import urlparse
from ldap.filter import filter_format
from flask import Blueprint, Flask, g, request
from flask_httpauth import HTTPBasicAuth
from flask_restplus import Api, Namespace, Resource, abort, reqparse
from werkzeug.contrib.fixers import ProxyFix
from univention.admin.uexceptions import authFail

from ..udm import UDM
from ..exceptions import NoSuperordinate, UdmError
from ..encoders import _classify_name
from ..helpers import get_all_udm_module_names
from .utils import setup_logging, ucr
from .resource_model import get_model, get_udm_module

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


def search_single_object(module_name, id, abort_on_error=True):  # type: (Text, Text, Optional[bool]) -> BaseObjectTV
	mod = get_udm_module(module_name=module_name, udm_api_version=UDM_API_VERSION)
	identifying_property = mod.meta.identifying_property
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


def url2dn(url):  # type: (Text) -> Text
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
	obj = search_single_object(module_name, obj_id, abort_on_error=False)
	if not obj:
		msg = 'Cannot find {!r} object in LDAP for {!r}.'.format(module_name, url)
		logger.error('422: %s', msg)
		abort(422, msg)
	return obj.dn


@auth.verify_password
def verify_pw(username, password):  # type: (Text, Text) -> bool
	logger.debug('*** username=%r password=%r', username, password)
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


def create_resource(module_name, namespace, api_model):  # type: (Text, Namespace, Model) -> Tuple[Any, Any]

	@namespace.route('/')
	@namespace.doc('{}ResourceList'.format(_classify_name(module_name)))
	class UdmResourceList(Resource):
		_udm_object_type = module_name
		method_decorators = (auth.login_required,)

		@namespace.doc('list')
		@namespace.marshal_list_with(api_model, skip_none=True)
		@docstring_params(_udm_object_type.split('/')[-1])
		def get(self):  # type: () -> Tuple[List[Dict[Text, Any]], int]
			"""List all {} objects."""
			logger.debug('UdmResourceList.get() self._udm_object_type=%r', self._udm_object_type)
			mod = get_udm_module(module_name=self._udm_object_type, udm_api_version=UDM_API_VERSION)
			identifying_property = mod.meta.identifying_property
			res = []
			for obj in mod.search():
				setattr(obj, 'id', getattr(obj.props, identifying_property))
				res.append(obj)
			if not res:
				msg = 'No {!r} objects exist.'.format(self._udm_object_type)
				logger.error('404: %s', msg)
				abort(404, msg)
			return res, 200

		@namespace.doc('create')
		@namespace.expect(api_model)
		@namespace.marshal_with(api_model, skip_none=True, code=201)
		@docstring_params(_udm_object_type.split('/')[-1])
		def post(self):  # type: () -> Tuple[Dict[Text, Any], int]
			"""Create a new {} object."""
			logger.debug('UdmResourceList.post() self._udm_object_type=%r', self._udm_object_type)
			mod = get_udm_module(module_name=self._udm_object_type, udm_api_version=UDM_API_VERSION)
			identifying_property = mod.meta.identifying_property
			parser = reqparse.RequestParser()
			parser.add_argument('options', type=list, help='Options of object [optional].')
			parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
			parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
			parser.add_argument('props', type=dict, required=True, help='Properties of object [required].')
			args = parser.parse_args()
			try:
				obj_id = args['props'][mod.meta.identifying_property]
			except KeyError:
				msg = 'ID of object is required in "props.{}".'.format(identifying_property)
				logger.error('400: %s', msg)
				abort(400, msg)
			obj = mod.new()  # type: BaseObjectTV
			obj.options = args.get('options') or []
			obj.policies = args.get('policies') or []
			obj.position = args.get('position') or mod._get_default_object_positions()[0]
			for k, v in args['props'].items():
				setattr(obj.props, k, v)
			logger.info('Creating {!r}...'.format(obj))
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
			"""Fetch a {} object given its name."""
			logger.debug('UdmResourceList.get() id=%r self._udm_object_type=%r', id, self._udm_object_type)
			logger.debug('*** g.get(udm)=%r', g.get('udm'))
			assert g.get('udm') is not None
			logger.debug('*** username=%r password=%r', request.authorization.username, request.authorization.password)
			obj = search_single_object(self._udm_object_type, id)
			return obj, 200

		@namespace.doc('delete')
		@namespace.response(204, 'Object deleted')
		@docstring_params(_udm_object_type.split('/')[-1])
		def delete(self, id):  # type: (Text) -> Tuple[Text, int]
			"""Delete a {} object given its name."""
			logger.debug('UdmResourceList.delete() id=%r self._udm_object_type=%r', id, self._udm_object_type)
			obj = search_single_object(self._udm_object_type, id)
			logger.info('Deleting {!r}...'.format(obj))
			obj.delete()
			return '', 204

		@namespace.doc('modify')
		@namespace.expect(api_model)
		@namespace.marshal_with(api_model, skip_none=True)
		@docstring_params(_udm_object_type.split('/')[-1])
		def put(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
			"""Update a {} object given its name."""
			logger.debug('UdmResourceList.put() id=%r self._udm_object_type=%r', id, self._udm_object_type)
			obj = search_single_object(self._udm_object_type, id)
			parser = reqparse.RequestParser()
			parser.add_argument('options', type=list, help='Options of object [optional].')
			parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
			parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
			parser.add_argument('props', type=dict, help='Properties of object [optional].')
			args = parser.parse_args()
			logger.info('Updating %r...', obj)
			changed = False
			for udm_attr in ('options', 'policies', 'position'):
				logger.debug('%s: %r', udm_attr, args.get(udm_attr))
				if args.get(udm_attr) is not None:
					# TODO
					setattr(obj, udm_attr, args[udm_attr])
					changed = True
			for prop, value in (args.get('props') or {}).iteritems():
				logger.debug('props.%s: %r', prop, value)
				if getattr(obj.props, prop) == '' and value is None:
					# Ignore values we set to None earlier (instead of ''), so they
					# wouldn't be shown in the API.
					continue
				obj_prop = getattr(obj.props, prop)
				try:
					encoder = obj.props._encoders[prop]  # type: BaseEncoderTV
				except KeyError:
					# logger.debug('%r: no encoder', prop)
					pass
				else:
					# logger.debug('encoder=%r', encoder)
					if hasattr(encoder.type_hint, '__iter__'):
						# nested object or list
						prop_type, content_desc = encoder.type_hint
						# logger.debug(
						# 	'prop_type(%s)=%r content_desc(%s)=%r',
						# 	type(prop_type), prop_type, type(content_desc), content_desc)
						is_list = prop_type in (list, 'ObjList')
						if isinstance(content_desc, dict):
							# logger.debug('content_desc is dict')
							pass
						elif content_desc == 'obj':
							if is_list:
								value = [url2dn(url) for url in value]
							else:
								value = url2dn(value)
						else:
							# logger.debug('content_desc is not dict or obj')
							pass
				if obj_prop != value:
					setattr(obj.props, prop, value)
					changed = True
			if changed:
				try:
					obj.save().reload()
				except UdmError as exc:
					logger.error('400: %s', exc)
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


if __name__ == '__main__':
	import logging
	logger.addHandler(logging.StreamHandler())
	app.run(debug=True, host='0.0.0.0', port=int(ucr.get('directory/manager/http_api/wsgi_server/port', 8999)))

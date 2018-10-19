from __future__ import absolute_import, unicode_literals
import logging
from ldap.filter import filter_format
from flask import Blueprint, Flask
from flask_restplus import Api, Namespace, Resource, abort, reqparse

from werkzeug.contrib.fixers import ProxyFix
from univention.config_registry import ConfigRegistry
from ..exceptions import UdmError
from .models import get_model, get_module

try:
	from typing import Any, Dict, List, Optional, Text, Tuple
	from univention.udm.base import BaseUdmObjectTV
except ImportError:
	pass


ucr = ConfigRegistry()
ucr.load()

UDM_API_VERSION = 1
HTTP_API_VERSION = '{}.0'.format(UDM_API_VERSION)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
blueprint = Blueprint('api', __name__, url_prefix='/udm')
api = Api(
	blueprint,
	version=HTTP_API_VERSION,
	title='UDM API',
	description='A simple UDM API',
)
_udm_object_type = 'users/user'
ns_users_user = Namespace(
	_udm_object_type.replace('/', '-'),
	description='{} related operations'.format(_udm_object_type)
)
api_model_users_user = ns_users_user.model(
	_udm_object_type.replace('/', '-'),
	get_model(module_name=_udm_object_type, udm_api_version=UDM_API_VERSION, api=ns_users_user)
)
api.add_namespace(ns_users_user, path='/{}'.format(_udm_object_type))
app.register_blueprint(blueprint)

LOG_MESSAGE_FORMAT ='%(asctime)s %(levelname)-7s %(module)s.%(funcName)s:%(lineno)d  %(message)s'
LOG_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
flask_rp_logger = logging.getLogger('flask_restplus')
gunicorn_logger = logging.getLogger('gunicorn')
udm_logger = logging.getLogger('univention')
for handler in app.logger.handlers:
	handler.setLevel(logging.DEBUG)
	handler.setFormatter(logging.Formatter(LOG_MESSAGE_FORMAT, LOG_DATETIME_FORMAT))
	flask_rp_logger.addHandler(handler)
	gunicorn_logger.addHandler(handler)
	udm_logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)
flask_rp_logger.setLevel(logging.DEBUG)
gunicorn_logger.setLevel(logging.DEBUG)
udm_logger.setLevel(logging.DEBUG)
logger = app.logger


def search_single_object(module_name, id):  # type: (Text, Text) -> BaseUdmObject
	mod = get_module(module_name=module_name, udm_api_version=UDM_API_VERSION)
	identifying_property = mod.meta.identifying_property
	filter_s = filter_format('%s=%s', (identifying_property, id))
	res = list(mod.search(filter_s))
	if len(res) == 0:
		msg = 'Object with id ({}) {!r} not found.'.format(identifying_property, id)
		logger.error('404: %s', msg)
		abort(404, msg)
	elif len(res) == 1:
		return res[0]
	else:
		logger.error('500: More than on %r object found, using filter %r.', module_name, filter_s)
		abort(500)


def obj2dict(obj):  # type: (BaseUdmObject) -> Dict[Text, Any]
	identifying_property = obj._udm_module.meta.identifying_property
	return {
		'id': getattr(obj.props, identifying_property),
		'dn': obj.dn,
		'options': obj.options,
		'policies': obj.policies,
		'position': obj.position,
		'props': obj.props,
	}


def docstring_params(*args, **kwargs):
	def dec_func(obj):
		obj.__doc__ = obj.__doc__.format(*args, **kwargs)
		return obj
	return dec_func


@ns_users_user.route('/')
class UsersUserList(Resource):
	_udm_object_type = 'users/user'

	@ns_users_user.doc('list')
	@ns_users_user.marshal_list_with(api_model_users_user, skip_none=True)
	@docstring_params(_udm_object_type.split('/')[-1])
	def get(self):  # type: () -> Tuple[List[Dict[Text, Any]], int]
		"""List all {} objects."""
		res = [obj2dict(obj) for obj in get_module(module_name=self._udm_object_type, udm_api_version=UDM_API_VERSION).search()]
		if not res:
			msg = 'No {!r} objects exist.'.format(self._udm_object_type)
			logger.error('404: %s', msg)
			abort(404, msg)
		return res, 200

	@ns_users_user.doc('create')
	@ns_users_user.expect(api_model_users_user)
	@ns_users_user.marshal_with(api_model_users_user, skip_none=True, code=201)
	@docstring_params(_udm_object_type.split('/')[-1])
	def post(self):  # type: () -> Tuple[Dict[Text, Any], int]
		"""Create a new {} object."""
		mod = get_module(module_name=self._udm_object_type, udm_api_version=UDM_API_VERSION)
		identifying_property = mod.meta.identifying_property
		parser = reqparse.RequestParser()
		parser.add_argument('id', type=str, required=True, help='ID ({}) of object [required].'.format(identifying_property))
		parser.add_argument('options', type=list, help='Options of object [optional].')
		parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
		parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
		parser.add_argument('props', type=dict, required=True, help='Properties of object [required].')
		args = parser.parse_args()
		obj = mod.new()  # type: BaseUdmObjectTV
		obj.options = args.get('options') or []
		obj.policies = args.get('policies') or []
		obj.position = args.get('position') or mod._get_default_object_positions()[0]
		for k, v in args['props'].items():
			setattr(obj.props, k, v)
		setattr(obj.props, mod.meta.identifying_property, args.get('id'))
		logger.info('Creating {!r}...'.format(obj))
		try:
			obj.save().reload()
		except UdmError as exc:
			logger.error('400: %s', exc)
			abort(400, str(exc))
		return obj2dict(obj), 201


@ns_users_user.route('/<string:id>')
@ns_users_user.response(404, 'User not found')
@ns_users_user.param('id', 'The objects ID (username, group name etc).')
class UsersUser(Resource):
	_udm_object_type = 'users/user'

	@ns_users_user.doc('get')
	@ns_users_user.marshal_with(api_model_users_user, skip_none=True)
	@docstring_params(_udm_object_type.split('/')[-1])
	def get(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
		"""Fetch a {} object given its usename."""
		obj = search_single_object(self._udm_object_type, id)
		return obj2dict(obj), 200

	@ns_users_user.doc('delete')
	@ns_users_user.response(204, 'User deleted')
	@docstring_params(_udm_object_type.split('/')[-1])
	def delete(self, id):  # type: (Text) -> Tuple[Text, int]
		"""Delete a {} object given its username."""
		obj = search_single_object(self._udm_object_type, id)
		logger.info('Deleting {!r}...'.format(obj))
		obj.delete()
		return '', 204

	@ns_users_user.doc('modify')
	@ns_users_user.expect(api_model_users_user)
	@ns_users_user.marshal_with(api_model_users_user, skip_none=True)
	@docstring_params(_udm_object_type.split('/')[-1])
	def put(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
		"""Update a {} object given its username."""
		obj = search_single_object(self._udm_object_type, id)
		parser = reqparse.RequestParser()
		parser.add_argument('options', type=list, help='Options of object [optional].')
		parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
		parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
		parser.add_argument('props', type=dict, help='Properties of object [optional].')
		args = parser.parse_args()
		logger.info('Updating {!r}...'.format(obj))
		changed = False
		for udm_attr in ('options', 'policies', 'position'):
			if args.get(udm_attr) is not None:
				setattr(obj, udm_attr, args[udm_attr])
				changed = True
		for prop, value in (args.get('props') or {}).iteritems():
			if getattr(obj.props, prop) == '' and value is None:
				# Ignore values we set to None earlier (instead of ''), so they
				# wouldn't be shown in the API.
				continue
			if getattr(obj.props, prop) != value:
				setattr(obj.props, prop, value)
				changed = True
		if changed:
			try:
				obj.save().reload()
			except UdmError as exc:
				logger.error('400: %s', exc)
				abort(400, str(exc))
		return obj2dict(obj), 200


if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=int(ucr.get('directory/manager/http_api/wsgi_server/port', 8999)))

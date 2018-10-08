from __future__ import absolute_import, unicode_literals
import logging
from ldap.filter import filter_format
from flask import Flask
from flask_restplus import Api, Resource, abort, reqparse
from werkzeug.contrib.fixers import ProxyFix
from univention.config_registry import ConfigRegistry
from .users_user import get_model, get_module

try:
	from typing import Any, Dict, List, Optional, Text, Tuple
	from univention.udm.base import BaseUdmObject
except ImportError:
	pass


LOG_MESSAGE_FORMAT ='%(asctime)s %(levelname)-7s %(module)s.%(funcName)s:%(lineno)d  %(message)s'
LOG_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter(LOG_MESSAGE_FORMAT, LOG_DATETIME_FORMAT))
flask_rp_logger = logging.getLogger('flask_restplus')
flask_rp_logger.setLevel(logging.DEBUG)
flask_rp_logger.addHandler(console_handler)
udm_logger = logging.getLogger('univention.udm')
udm_logger.setLevel(logging.DEBUG)
udm_logger.addHandler(console_handler)
logger = logging.getLogger(__name__)
if __name__ == '__main__':
	logger.setLevel(logging.DEBUG)
	logger.addHandler(console_handler)

ucr = ConfigRegistry()
ucr.load()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
api = Api(app, version='1.0', title='UDM users/user API', description='A simple UDM users/user API')
ns = api.namespace('users/user', description='Operations on users/user objects.')
users_user_api_model = ns.model('UsersUser', get_model(module_name='users/user', api=api))


def search_single_object(module_name, id):  # type: (Text, Text) -> BaseUdmObject
	mod = get_module(module_name=module_name)
	identifying_property = mod.meta.identifying_property
	filter_s = filter_format('%s=%s', (identifying_property, id))
	res = list(mod.search(filter_s))
	if len(res) == 0:
		abort(404, 'Object with id ({}) {!r} not found.'.format(identifying_property, id))
	elif len(res) == 1:
		return res[0]
	else:
		logger.error('More than on %r object found, using filter %r.', module_name, filter_s)
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


@ns.route('/')
class UsersUserList(Resource):
	"""Shows a list of all todos, and lets you POST to add new tasks"""
	@ns.doc('list_users_user')
	@ns.marshal_list_with(users_user_api_model, skip_none=True)
	def get(self):  # type: () -> Tuple[List[Dict[Text, Any]], int]
		"""List all users/user"""
		res = []
		for obj in get_module(module_name='users/user').search():
			if len(res) > 2:  # TODO: remove this
				break
			res.append(obj2dict(obj))
		if not res:
			abort(404, 'No {!r} objects exist.'.format('users/user'))
		return res, 200

	@ns.doc('create_users_user')
	@ns.expect(users_user_api_model)
	@ns.marshal_with(users_user_api_model, skip_none=True, code=201)
	def post(self):  # type: () -> Tuple[Dict[Text, Any], int]
		"""Create a new users/user"""
		logger.debug('UsersUserList.post() api.payload={!r}'.format(api.payload))
		mod = get_module(module_name='users/user')
		identifying_property = mod.meta.identifying_property
		parser = reqparse.RequestParser()
		parser.add_argument('id', type=str, required=True, help='ID ({}) of object [required].'.format(identifying_property))
		parser.add_argument('options', type=list, help='Options of object [optional].')
		parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
		parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
		parser.add_argument('props', type=dict, required=True, help='Properties of object [required].')
		args = parser.parse_args()
		logger.debug('UsersUserList.post() args={!r}'.format(args))
		obj = mod.new()  # type: BaseUdmObject
		obj.options = args.get('options') or []
		obj.policies = args.get('policies') or []
		obj.position = args.get('position') or 'cn=users,{}'.format(ucr['ldap/base'])
		obj.props = args['props']
		setattr(obj.props, mod.meta.identifying_property, args.get('id'))
		logger.info('Creating {!r}...'.format(obj))
		obj.save().reload()
		return obj2dict(obj), 201


@ns.route('/<string:id>')
@ns.response(404, 'User not found')
@ns.param('id', 'The objects ID (username, group name etc).')
class UsersUser(Resource):
	"""Show a single users/user item and lets you delete them"""

	@ns.doc('get_users_user')
	@ns.marshal_with(users_user_api_model, skip_none=True)
	def get(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
		"""Fetch a given resource"""
		obj = search_single_object('users/user', id)
		return obj2dict(obj), 200

	@ns.doc('delete_users_user')
	@ns.response(204, 'User deleted')
	def delete(self, id):  # type: (Text) -> Tuple[Text, int]
		"""Delete a user given its username"""
		obj = search_single_object('users/user', id)
		logger.info('Deleting {!r}...'.format(obj))
		obj.delete()
		return '', 204

	@ns.expect(users_user_api_model)
	@ns.marshal_with(users_user_api_model, skip_none=True)
	def put(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
		"""Update a user given its username"""
		logger.debug('UsersUser.put() id={!r} api.payload={!r}'.format(id, api.payload))
		obj = search_single_object('users/user', id)
		parser = reqparse.RequestParser()
		parser.add_argument('options', type=list, help='Options of object [optional].')
		parser.add_argument('policies', type=list, help='Policies applied to object [optional].')
		parser.add_argument('position', type=str, help='Position of object in LDAP [optional].')
		parser.add_argument('props', type=dict, help='Properties of object [optional].')
		args = parser.parse_args()
		logger.debug('UsersUserList.put() args={!r}'.format(args))
		logger.info('Updating {!r}...'.format(obj))
		obj.options = args.get('options') or obj.options
		obj.policies = args.get('policies') or obj.policies
		obj.position = args.get('position') or obj.position
		logger.debug('UsersUserList.put() 0 obj.props={!r}'.format(obj.props))
		for prop, value in (args.get('props') or {}).items():
			if getattr(obj.props, prop) == '' and value is None:
				# Ignore values we set to None earlier (instead of ''), so they
				# wouldn't be shown in the API.
				logger.debug(
					'UsersUserList.put() ignoring prop=%r getattr(obj.props, prop)=%r value=%r',
					prop, getattr(obj.props, prop), value)
				continue
			if getattr(obj.props, prop) != value:
				logger.debug(
					'UsersUserList.put() setting prop=%r getattr(obj.props, prop)=%r value=%r',
					prop, getattr(obj.props, prop), value)
				setattr(obj.props, prop, value)
		logger.debug('UsersUserList.put() 1 obj.props={!r}'.format(obj.props))
		obj.save()
		return obj2dict(obj), 201


if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)

from __future__ import absolute_import, unicode_literals
import logging
from ldap.filter import filter_format
from flask import Flask
from flask_restplus import Api, Resource, reqparse
from werkzeug.contrib.fixers import ProxyFix
from univention.config_registry import ConfigRegistry
from univention.udm.http_api.users_user import get_model, get_module

try:
	from typing import Any, Dict, List, Optional, Text, Tuple
	from univention.udm.base import BaseUdmObject
except ImportError:
	pass


console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
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


@ns.route('/')
class UsersUserList(Resource):
	"""Shows a list of all todos, and lets you POST to add new tasks"""
	@ns.doc('list_users_user')
	@ns.marshal_list_with(users_user_api_model, skip_none=True)
	def get(self):  # type: () -> List[Dict[Text, Any]]
		"""List all users/user"""
		res = []
		for obj in get_module(module_name='users/user').search():
			if len(res) > 2:  # TODO: remove this
				break
			res.append({
				'id': getattr(obj.props, obj._udm_module.meta.identifying_property),
				'dn': obj.dn,
				'options': obj.options,
				'policies': obj.policies,
				'position': obj.position,
				'props': obj.props,
			})
		return res

	@ns.doc('create_users_user')
	@ns.expect(users_user_api_model)
	@ns.marshal_with(users_user_api_model, skip_none=True, code=201)
	def post(self):  # type: () -> Tuple[Dict[Text, Any], int]
		"""Create a new users/user"""
		logger.debug('UsersUserList.post() api.payload={!r}'.format(api.payload))
		parser = reqparse.RequestParser()
		parser.add_argument('props', type=dict, required=True, help='Properties of user [required].')
		args = parser.parse_args()
		logger.debug('UsersUserList.post() args={!r}'.format(args))
		mod = get_module(module_name='users/user')
		identifying_property = mod.meta.identifying_property
		obj = mod.new()  # type: BaseUdmObject
		obj.options = args.get('options') or []
		obj.policies = args.get('policies') or []
		obj.position = args.get('position') or 'cn=users,{}'.format(ucr['ldap/base'])
		obj.props = args['props']
		obj.save().reload()
		res = {
			'id': getattr(obj.props, identifying_property),
			'dn': obj.dn,
			'options': obj.options,
			'policies': obj.policies,
			'position': obj.position,
			'props': obj.props,
		}
		return res, 201


@ns.route('/<string:id>')
@ns.response(404, 'User not found')
@ns.param('id', 'The objects ID (username, group name etc).')
class UsersUser(Resource):
	"""Show a single users/user item and lets you delete them"""

	@ns.doc('get_users_user')
	@ns.marshal_with(users_user_api_model, skip_none=True)
	def get(self, id):  # type: (Text) -> Dict[Text, Any]
		"""Fetch a given resource"""
		mod = get_module(module_name='users/user')
		identifying_property = mod.meta.identifying_property
		res = list(mod.search(filter_format('%s=%s', (identifying_property, id))))
		if len(res) == 1:
			ret = {
				'id': getattr(res[0].props, identifying_property),
				'dn': res[0].dn,
				'options': res[0].options,
				'policies': res[0].policies,
				'position': res[0].position,
				'props': res[0].props,
			}
			return ret
		else:
			raise Exception('get(): zero or more than one result when searching for id={!r}: {!r}'.format(id, res))

	@ns.doc('delete_users_user')
	@ns.response(204, 'User deleted')
	def delete(self, id):  # type: (Text) -> Tuple[Text, int]
		"""Delete a user given its username"""
		mod = get_module(module_name='users/user')
		identifying_property = mod.meta.identifying_property
		res = list(mod.search(filter_format('%s=%s', (identifying_property, id))))
		if len(res) == 1:
			logger.info('Deleting {!r}.'.format(res[0]))
			res[0].delete()
		else:
			raise Exception('delete(): zero or more than one result when searching for id={!r}: {!r}'.format(id, res))
		return '', 204

	@ns.expect(users_user_api_model)
	@ns.marshal_with(users_user_api_model, skip_none=True)
	def put(self, id):  # type: (Text) -> Dict[Text, Any]
		"""Update a user given its username"""
		logger.debug('UsersUser.put() id={!r} api.payload={!r}'.format(id, api.payload))
		mod = get_module(module_name='users/user')
		identifying_property = mod.meta.identifying_property
		res = list(mod.search(filter_format('%s=%s', (identifying_property, id))))
		logger.debug('UsersUser.put() res={!r}'.format(res))
		if len(res) == 1:
			# TODO: update props of res[0]
			ret = {
				'id': getattr(res[0].props, identifying_property),
				'dn': res[0].dn,
				'options': res[0].options,
				'policies': res[0].policies,
				'position': res[0].position,
				'props': res[0].props,
			}
			return ret
		else:
			raise Exception('put(): zero or more than one result when searching for id={!r}: {!r}'.format(id, res))


if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)

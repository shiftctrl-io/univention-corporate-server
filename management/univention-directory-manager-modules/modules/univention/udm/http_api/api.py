from __future__ import absolute_import, unicode_literals
from ldap.filter import filter_format
from flask import Flask
from flask_restplus import Api, Resource, fields
from werkzeug.contrib.fixers import ProxyFix
from univention.udm.http_api.users_user import get_model, get_module


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
api = Api(app, version='1.0', title='UDM users/user API', description='A simple UDM users/user API')
ns = api.namespace('users/user', description='users/user operations')
users_user_api_model = api.model('UsersUser', get_model())


@ns.route('/')
class UsersUserList(Resource):
	"""Shows a list of all todos, and lets you POST to add new tasks"""
	@ns.doc('list_users_user')
	@ns.marshal_list_with(users_user_api_model)
	def get(self):
		"""List all users/user"""
		res = []
		for user in get_module().search():
			res.append(user.props.__dict__)
			res[-1]['dn'] = user.dn
			if len(res) > 2:
				break
		return res

	@ns.doc('create_users_user')
	@ns.expect(users_user_api_model)
	@ns.marshal_with(users_user_api_model, code=201)
	def post(self):
		"""Create a new users/user"""
		print('UsersUserList.post() api.payload={!r}'.format(api.payload))
		obj = get_module().new()
		# TODO: set props
		res = obj.props.__dict__
		res['dn'] = obj.dn
		return res, 201


@ns.route('/<string:uid>')
@ns.response(404, 'User not found')
@ns.param('uid', 'The username')
class UsersUser(Resource):
	"""Show a single users/user item and lets you delete them"""
	@ns.doc('get_users_user')
	@ns.marshal_with(users_user_api_model)
	def get(self, uid):
		"""Fetch a given resource"""
		print('UsersUser.get() uid={!r}'.format(uid))
		res = list(get_module().search(filter_format('uid=%s', (uid,))))
		print('UsersUser.get() res={!r}'.format(res))
		if len(res) == 1:
			ret = res[0].props.__dict__
			ret['dn'] = res[0].dn
			return ret
		else:
			raise Exception('get(): zero or more than one result when searching for uid={!r}: {!r}'.format(uid, res))

	@ns.doc('delete_users_user')
	@ns.response(204, 'Todo deleted')
	def delete(self, uid):
		"""Delete a user given its username"""
		print('UsersUser.delete() uid={!r}'.format(uid))
		res = list(get_module().search(filter_format('uid=%s', (uid,))))
		print('UsersUser.delete() res={!r}'.format(res))
		if len(res) == 1:
			res[0].delete()
		else:
			raise Exception('delete(): zero or more than one result when searching for uid={!r}: {!r}'.format(uid, res))
		return '', 204

	@ns.expect(users_user_api_model)
	@ns.marshal_with(users_user_api_model)
	def put(self, uid):
		"""Update a user given its username"""
		print('UsersUser.put() uid={!r} api.payload={!r}'.format(uid, api.payload))
		res = list(get_module().search(filter_format('uid=%s', (uid,))))
		print('UsersUser.put() res={!r}'.format(res))
		if len(res) == 1:
			# TODO: update props of res[0]
			ret = res[0].reload().props.__dict__
			ret['dn'] = res[0].dn
			return ret
		else:
			raise Exception('put(): zero or more than one result when searching for uid={!r}: {!r}'.format(uid, res))


if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)

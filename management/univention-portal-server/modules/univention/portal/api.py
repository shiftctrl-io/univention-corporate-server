from __future__ import absolute_import, unicode_literals

import re
import logging
import urllib
import urlparse
import datetime
import operator
from six import string_types
from ldap.filter import filter_format
from flask import Blueprint, Flask, g, redirect, request
from flask_httpauth import HTTPBasicAuth
import flask_login
from flask_restplus import Api, Namespace, Resource, abort, reqparse
from werkzeug.contrib.fixers import ProxyFix
from univention.admin.uexceptions import valueInvalidSyntax

from univention.udm import UDM
from univention.udm.exceptions import ConnectionError, MultipleObjects, NoObject, NoSuperordinate, UdmError
from univention.udm.encoders import _classify_name
from univention.udm.http_api.utils import get_identifying_property, setup_logging, ucr
from univention.portal.resource_model import get_base_model, get_specific_model

try:
	from typing import Any, Dict, Iterable, List, Optional, Text, Tuple, Union
	from univention.udm.base import BaseObjectTV
	from univention.udm.encoders import BaseEncoderTV
	from flask_restplus import Model
except ImportError:
	pass


UDM_API_VERSION = 1
HTTP_API_VERSION = '{}.0'.format(UDM_API_VERSION)

_url2module = {}  # type: Dict[Text, Text]
_uri_regex = re.compile(r'^(https{0,1}?)://(.+?)/udm/(\w+?)/(\w+?)/(.*)')

# https://swagger.io/docs/specification/2-0/authentication/
# authorizations = {
# 	'basic': {'type': 'basic'}
# }
auth = HTTPBasicAuth()

app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'  # TODO: joinscript: create and store in file
setup_logging(app)
logger = logging.getLogger(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
blueprint = Blueprint('api', __name__, url_prefix='/portal')
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(minutes=5)
login_manager = flask_login.LoginManager()
login_manager.init_app(app)
login_manager.login_view = '{}/login'.format(blueprint.url_prefix)

udm_machine = UDM.machine().version(UDM_API_VERSION)


class ApiUser(flask_login.UserMixin):
	obj = None  # type: BaseObjectTV

	def get_id(self):
		return self.obj.props.username


@login_manager.user_loader
def load_user(username):
	logger.debug('** load_user(%r)', username)
	try:
		obj = udm_machine.get('users/user').get_by_id(username)
	except (NoObject, MultipleObjects):
		return None

	user = ApiUser()
	user.obj = obj
	return user


def verify_and_get_user(username, password):  # type: (Text, Text) -> Union[ApiUser, None]
	logger.debug('*** username=%r password=%r', username, password)
	if g.get('user'):
		logger.error('Already set: g.user=%r', g.user)
		abort(500)
	if not username or not password:
		return None
	user = load_user(username)
	if not user:
		return None
	try:
		UDM.credentials(user.obj.dn, password)  # noqa
	except ConnectionError:
		return None
	else:
		g.user = user.obj
		return user


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
	next_url = request.args.get('next_url', blueprint.url_prefix)
	logger.debug('*** login() next_url=%r request.method=%r request.form.items()=%r', next_url, request.method, request.form.items())
	if request.method == 'POST':
		user = verify_and_get_user(request.form['username'], request.form['password'])
		if user:
			assert user.obj.props.username == request.form['username']
			flask_login.login_user(user)
			logger.info('Logged in %r.', user.obj.props.username)
			return redirect(next_url)
		else:
			msg = 'Bad username or password.'
			logger.info(msg)
			abort(401, msg)
	else:
		return redirect('/')


@flask_login.login_required
@blueprint.route('/logout')
def logout():
	logger.debug('** logout()')
	flask_login.logout_user()
	return redirect(blueprint.url_prefix)


api = Api(
	blueprint,
	version=HTTP_API_VERSION,
	title='Portal API',
	description='Portal API',
	# authorizations=authorizations,
	# security='basic',
)
app.register_blueprint(blueprint)


def search_single_object(udm, module_name, id, abort_on_error=True):
	# type: (UDM, Text, Text, Optional[bool]) -> BaseObjectTV
	mod = udm.get(module_name)
	_idl, identifying_property = get_identifying_property(mod)

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


list_parser = reqparse.RequestParser()
list_parser.add_argument('edit_mode', type=bool, location='args', dest='edit_mode', help='send all objects [optional].')
list_parser.add_argument('Accept-Language', type=str, location='headers', dest='language', help='Language [optional].')
get_parser = reqparse.RequestParser()
get_parser.add_argument('Accept-Language', type=str, location='headers', dest='language', help='Language [optional].')
modify_parser = reqparse.RequestParser()
modify_parser.add_argument('props', type=dict, help='Properties of object [optional].')


def create_resource(module_name, namespace, api_model, methods):
	# type: (Text, Namespace, Model, Iterable[Text]) -> Tuple[Any, Any]

	@namespace.route('/')
	@namespace.doc('{}ResourceList'.format(_classify_name(module_name)))
	class UdmResourceList(Resource):
		_udm_object_type = module_name
		# method_decorators = (auth.login_required,)

		if 'list' in methods:
			@namespace.doc('list')
			@namespace.marshal_list_with(api_model, skip_none=True)
			@api.expect(list_parser)
			@docstring_params(_udm_object_type.split('/')[-1])
			def get(self):  # type: () -> Tuple[List[Dict[Text, Any]], int]
				"""List all {} objects."""
				args = list_parser.parse_args()
				logger.debug('UdmResourceList.get() g.get("user")=%r self._udm_object_type=%r args=%r', g.get('user'), self._udm_object_type, args)
				edit_mode = bool(args.get('edit_mode'))
				language = args.get('language')
				logger.debug('UdmResourceList.get() edit_mode=%r language("Accept-Language")=%r', edit_mode, language)
				mod = udm_machine.get(self._udm_object_type)
				_idl, identifying_property = get_identifying_property(mod)
				if self._udm_object_type == 'settings/portal':
					portal = UdmResource._get_portal()
					new_content = []
					for cat, entries in portal.props.content:
						new_entries = []
						for entry_dn in entries:
							entry = udm_machine.get('settings/portal_entry').get(entry_dn)
							if UdmResource._may_view_entry(entry, g.get('user'), edit_mode):
								new_entries.append(entry)
						if len(new_entries) == 0:
							continue
						entries = [obj.dn for obj in new_entries]
						new_content.append((cat, entries))
					portal.props.content = new_content
					setattr(portal, 'id', getattr(portal.props, identifying_property))
					UdmResource._l10(portal, language)
					return [portal], 200

				res = []
				try:
					for obj in mod.search():
						if self._udm_object_type == 'settings/portal_entry':
							if not UdmResource._may_view_entry(obj, g.get('user'), edit_mode):
								continue
						setattr(obj, 'id', getattr(obj.props, identifying_property))
						UdmResource._l10(obj, language)
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

		if 'create' in methods:
			@flask_login.login_required
			@namespace.doc('create')
			@namespace.expect(api_model)
			@namespace.marshal_with(api_model, skip_none=True, code=201)
			@api.expect(modify_parser)
			@docstring_params(_udm_object_type.split('/')[-1])
			def post(self):  # type: () -> Tuple[Dict[Text, Any], int]
				"""Create a new {} object."""
				logger.debug('UdmResourceList.post() self._udm_object_type=%r', self._udm_object_type)
				mod = udm_machine.get(self._udm_object_type)
				_idl, identifying_property = get_identifying_property(mod)
				args = modify_parser.parse_args()
				try:
					obj_id = args['props'][identifying_property]
				except KeyError:
					msg = 'ID of object is required in "props.{}".'.format(identifying_property)
					logger.error('400: %s', msg)
					abort(400, msg)
				logger.info('Creating %r object with args %r...', self._udm_object_type, args)
				superordinate_url = args.get('superordinate')
				superordinate_dn = url2dn(udm_machine, superordinate_url) if superordinate_url else None
				try:
					obj = mod.new(superordinate_dn)  # type: BaseObjectTV
					obj.options = ["default"]
					obj.policies = []
					obj.position = mod._get_default_object_positions()[0]
					obj.superordinate = 'cn=univention,{}'.format(ucr['ldap/base'])
					for prop, value in UdmResource._udmify_arg_props(obj, args).iteritems():
						setattr(obj.props, prop, value)
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
		# method_decorators = (auth.login_required,)

		if 'get' in methods:
			@namespace.doc('get')
			@namespace.marshal_with(api_model, skip_none=True)
			@docstring_params(_udm_object_type.split('/')[-1])
			def get(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
				"""Fetch a {} object."""
				logger.debug('UdmResourceList.get() id=%r self._udm_object_type=%r', id, self._udm_object_type)
				args = get_parser.parse_args()
				obj = search_single_object(udm_machine, self._udm_object_type, id)
				if not self._may_view_entry(obj, g.get('user'), True):
					abort(404)
				language = args.get('language')
				logger.debug('UdmResource.get() language("Accept-Language")=%r', language)
				self._l10(obj, language)
				return obj, 200

		if 'delete' in methods:
			@flask_login.login_required
			@namespace.doc('delete')
			@namespace.response(204, 'Object deleted')
			@docstring_params(_udm_object_type.split('/')[-1])
			def delete(self, id):  # type: (Text) -> Tuple[Text, int]
				"""Delete a {} object from the hosts portal."""
				logger.debug('UdmResourceList.delete() id=%r self._udm_object_type=%r', id, self._udm_object_type)
				obj = search_single_object(udm_machine, self._udm_object_type, id)
				if not self._may_edit_obj(obj, g.user):
					abort(404)
				portal = self._get_portal()
				logger.debug('UdmResourceList.delete() removing %r from %r...', obj, portal)
				content = portal.props.content
				new_content = []
				for cat, entries in content:
					if self._udm_object_type == 'settings/portal_entry':
						if obj.dn in entries:
							entries.remove(obj.dn)
							if not entries:
								continue
						new_content.append((cat, entries))
					elif self._udm_object_type == 'settings/portal_category':
						if cat == obj.dn:
							continue
						new_content.append((cat, entries))
					else:
						abort(500, 'Unkown module {!r}.'.format(self._udm_object_type))
				portal.props.content = new_content
				portal.save()
				return '', 204

		if 'modify' in methods:
			@flask_login.login_required
			@namespace.doc('modify')
			@namespace.expect(api_model)
			@namespace.marshal_with(api_model, skip_none=True)
			@api.expect(modify_parser)
			@docstring_params(_udm_object_type.split('/')[-1])
			def put(self, id):  # type: (Text) -> Tuple[Dict[Text, Any], int]
				"""Update a {} object."""
				logger.debug('UdmResourceList.put(id=%r) self._udm_object_type=%r', id, self._udm_object_type)
				args = modify_parser.parse_args()
				obj = search_single_object(udm_machine, self._udm_object_type, id)
				logger.info('Updating %r with args %r...', obj, args)
				changed = False
				if obj.policies and isinstance(obj.policies, list):
					obj.policies = [
						url2dn(udm_machine, url) for url in obj.policies
						if isinstance(url, string_types) and _uri_regex.match(url)
					]
				if obj.superordinate and isinstance(obj.superordinate, string_types) and _uri_regex.match(obj.superordinate):
					obj.superordinate = url2dn(udm_machine, obj.superordinate)
				for prop, value in self._udmify_arg_props(obj, args).iteritems():
					old_value = getattr(obj.props, prop)
					if old_value != value:
						logger.debug('(%s) Setting props.%s to %r (old_value=%r).', id, prop, value, old_value)
						try:
							setattr(obj.props, prop, value)
						except UdmError as exc:
							logger.error('400: (%s) %s', id, exc)
							abort(400, str(exc))
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

		@staticmethod
		def _udmify_arg_props(obj, args):  # type: (BaseObjectTV, Dict[Text, Any]) -> Dict[Text, Any]
			res = {}
			for prop, value in (args.get('props') or {}).iteritems():
				# logger.debug('*** props.%s: %r', prop, value)
				if getattr(obj.props, prop) == '' and value is None:
					# Ignore values we set to None earlier (instead of ''), so they
					# wouldn't be shown in the API.
					continue
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
								value = [url2dn(udm_machine, url) for url in value]
							else:
								value = url2dn(udm_machine, value)
						else:
							pass
					elif encoder.type_hint == 'obj':
						# Obj2UrlField
						value = url2dn(udm_machine, value)
					elif encoder.type_hint == datetime.date:
						value = datetime.datetime.strptime(value, '%Y-%m-%d').date()
				res[prop] = value
			return res

		@staticmethod
		def _l10(obj, lang):  # type: (BaseObjectTV, Text) -> None
			def get_lang_code(lang):  # type: (Text) -> Text
				if not lang:
					return ''
				langs = lang.split(',')
				if not langs:
					return ''
				res = []
				for l in langs:
					try:
						language, prio = l.split(';', 1)
					except ValueError:
						language, prio = l, 1
					res.append((prio, language))
				return sorted(res, key=operator.itemgetter(0))[0][1]

			lang_code = get_lang_code(lang)
			if lang_code:
				lang_code = lang_code.replace('-', '_')

			for attr in ('displayName', 'description'):
				prop = getattr(obj.props, attr, None)
				if prop and isinstance(prop, dict):
					if lang_code in prop:
						obj.props.__dict__['{}_l10n'.format(attr)] = prop[lang_code]
					elif 'en_US' in prop:
						obj.props.__dict__['{}_l10n'.format(attr)] = prop['en_US']
					else:
						obj.props.__dict__['{}_l10n'.format(attr)] = prop.values()[0]

		@staticmethod
		def _get_portal():
			localhost = udm_machine.obj_by_dn(ucr.get('ldap/hostdn'))
			return localhost.props.portal.obj

		@classmethod
		def _is_admin(cls, user):
			if user is None:
				logger.debug('** _is_admin(%r)=False', user)
				return False
			admin_group_name = ucr.get('groups/default/domainadmins', 'Domain Admins')
			admins = udm_machine.get('groups/group').get_by_id(admin_group_name)
			logger.debug('** _is_admin(%r)=%r', user, admins.dn in user.props.groups)
			return admins.dn in user.props.groups

		@classmethod
		def _may_view_entry(cls, entry, user, edit_mode):
			if edit_mode and cls._is_admin(user):
				return True
			# TODO
			return False

		@classmethod
		def _may_edit_obj(cls, entry, user):
			return cls._is_admin(user)

		@classmethod
		def _may_edit_objs(cls, module_name, user):
			return cls._is_admin(user)

	return UdmResourceList, UdmResource


udm_modules = {
	'settings/portal': ('list', 'get', 'modify'),
	'settings/portal_category': ('list', 'create', 'get', 'delete', 'modify'),
	'settings/portal_entry': ('list', 'create', 'get', 'delete', 'modify'),
}

base_model = get_base_model(api)

for udm_object_type, methods in udm_modules.items():
	ns = Namespace(udm_object_type.replace('/', '_'), description='{} related operations'.format(udm_object_type))
	try:
		udm_model = get_specific_model(module_name=udm_object_type, udm_api_version=UDM_API_VERSION, api=ns)
	except NoSuperordinate as exc:
		logger.warn(exc)
		continue
	ns_model = ns.inherit(udm_object_type.replace('/', '_'), base_model, udm_model)
	api.add_namespace(ns, path='/{}'.format(udm_object_type))
	create_resource(udm_object_type, ns, ns_model, methods)
	_url2module['{}/{}'.format(blueprint.url_prefix, api.get_ns_path(ns).strip('/'))] = udm_object_type


def main():
	import logging
	logger.addHandler(logging.StreamHandler())
	app.run(debug=True, host='0.0.0.0', port=int(ucr.get('directory/manager/http_api/wsgi_server/port', 8999)))
	g.user = None


if __name__ == '__main__':
	main()

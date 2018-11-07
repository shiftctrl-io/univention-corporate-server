#!/usr/bin/python2.7

import time
import random
import string
try:
	from univention.udm import UDM
	running_on_ucs = True
except ImportError:
	running_on_ucs = False
import requests
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
from bravado.exception import HTTPUnauthorized


HOST = '10.20.30.5'
PORT = 80
SCHEME = 'http'
SWAGGER_URL = '{}://{}:{}/udm/swagger.json'.format(SCHEME, HOST, PORT)


def random_str():
	return ''.join(random.choice(string.ascii_letters) for _ in range(8))


# TIMING
t0 = time.time()
req_result = requests.get(SWAGGER_URL)
print('Time to retrieve swagger schema: {:0.2f}s.'.format(time.time() - t0))
swagger_spec = req_result.json()
t0 = time.time()
SwaggerClient.from_spec(swagger_spec, SWAGGER_URL)
print('Time to create client from swagger schema: {:0.2f}s.'.format(time.time() - t0))

# CHECK AUTH
client = SwaggerClient.from_url(SWAGGER_URL)
try:
	users = client.users_user.list().result()
	raise Exception('Could make request without authenticating!')
except HTTPUnauthorized:
	pass
http_client = RequestsClient()
http_client.set_basic_auth(HOST, 'Administrator', 'univention')
client = SwaggerClient.from_url(SWAGGER_URL, http_client=http_client)

# LIST
users = client.users_user.list().result()
print('Got {} users.'.format(len(users)))

# GET
username = users[-1].props.username
user = client.users_user.get(id=username).result()
print('Unixhome of user {!r} is {!r}.'.format(user.props.username, user.props.unixhome))

# GET with fields mask
# -H "accept: application/json" -H "X-Fields: props{username, groups},position"
fields_mask = 'uri, position, props{username, groups}'
user = client.users_user.get(id=username, _request_options={'headers': {'X-Fields': fields_mask}}).result()
print('User resource with fields mask {!r} should have emtpy "options" property...'.format(fields_mask))
assert user.options is None
print('OK.')

# CREATE
hpa = [
	{'street': random_str(), 'zipcode': random_str(), 'city': random_str()},
	{'street': random_str(), 'zipcode': random_str(), 'city': random_str()},
]
udm_attrs = {
	'firstname': random_str(),
	'lastname': random_str(),
	'username': random_str(),
	'password': random_str(),
	'homePostalAddress': hpa,
}
user_new = client.users_user.create(payload={
	'id': udm_attrs['username'],
	'props': udm_attrs,
}).result()
# print('New user: {!r}\n'.format(user))
assert user_new.id == udm_attrs['username']

user = client.users_user.get(id=udm_attrs['username']).result()
print('Verifying result...')
for k, v in udm_attrs.items():
	if k == 'password':
		continue
	print('Checking {!r}...'.format(k))
	if isinstance(v, list):
		# homePostalAddress
		res = [_hpa.__dict__['_Model__dict'] for _hpa in getattr(user.props, k)]
		assert sorted(res) == sorted(v), 'Expected for {!r}: {!r} Got: {!r}'.format(k, v, res)
	else:
		res = getattr(user.props, k)
		assert res == v, 'Expected for {!r}: {!r} Got: {!r}'.format(k, v, res)
	print('OK: {!r}'.format(k))

# compare object result and dict result
dict_client = SwaggerClient.from_url(SWAGGER_URL, http_client=http_client, config={'use_models': False})
dict_user = dict_client.users_user.get(id=udm_attrs['username']).result()
# print('New user as dict: {!r}\n'.format(dict_user))
print('Comparing object result and dict result...')
for udm_attr in ('options', 'policies', 'position'):
	if dict_user[udm_attr] != getattr(user, udm_attr):
		raise Exception('{}: {!r} != {!r}'.format(udm_attr, dict_user[udm_attr], getattr(user, udm_attr)))
for prop, value in user.props.__dict__.iteritems():
	if prop == '_Model__dict':
		continue
	if getattr(user.props, prop) == '' and value is None:
		# Ignore values we set to None earlier (instead of ''), so they
		# wouldn't be shown in the API.
		continue
	if dict_user['props'][prop] != getattr(user.props, prop):
		raise Exception('{}: {!r} != {!r}'.format(prop, dict_user['props'][prop], getattr(user.props, prop)))
print('OK: object result == dict result')

if running_on_ucs:
	# compare object result and UDM object loaded from LDAP
	udm_obj = UDM.admin().version(1).get('users/user').get(user.dn)
	print('Comparing UDM object and HTTP (object) result...')
	for udm_attr in ('options', 'policies', 'position'):
		if getattr(udm_obj, udm_attr) != getattr(user, udm_attr):
			raise Exception('{}: {!r} != {!r}'.format(udm_attr, getattr(udm_obj, udm_attr), getattr(user, udm_attr)))
	for prop, value in user.props.__dict__.iteritems():
		if prop == '_Model__dict':
			continue
		if getattr(user.props, prop) == '' and value is None:
			# Ignore values we set to None earlier (instead of ''), so they
			# wouldn't be shown in the API.
			continue
		if getattr(udm_obj.props, prop) != getattr(user.props, prop):
			raise Exception('{}: {!r} != {!r}'.format(prop, getattr(udm_obj.props, prop), getattr(user.props, prop)))
	print('OK: UDM object == HTTP (object) result')

dom_users = client.groups_group.get(id='Domain Users').result()
assert user.uri in dom_users.props.users, 'Users URI ({!r}) not in "Domain Users" property "users": {!r}.'.format(
	user.uri, dom_users.props.users)
print('OK: found users URI in "Domain Users" property "users".')

# MODIFY
old_unixhome = user.props.unixhome
print('Old unixhome of user {!r} is {!r}.'.format(user.props.username, old_unixhome))
modification = {'props': {'unixhome': '{}2'.format(user.props.unixhome)}}
user = client.users_user.modify(id=user.props.username, payload=modification).result()
user2 = client.users_user.get(id=udm_attrs['username']).result()
assert user.props.unixhome == user2.props.unixhome, 'Result object is was not updated.'
print('OK: Result object is up2date, unixhome={!r}'.format(user.props.unixhome))
assert user.props.unixhome == '{}2'.format(old_unixhome), 'User was not modified.'
print('OK: new unixhome of user {!r} is {!r}.'.format(user.props.username, user.props.unixhome))

# DELETE
result = client.users_user.delete(id=user.props.username).result()
print('OK: Result of deleting user {!r} is {!r} (no exception was raised).'.format(user.props.username, result))

print('All tests OK.')

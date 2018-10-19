import random
import string
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
from bravado.exception import HTTPUnauthorized


HOST = '10.20.30.5'
SCHEME = 'http'
SWAGGER_URL = '{}://{}/udm/swagger.json'.format(SCHEME, HOST)


def random_str():
	return ''.join(random.choice(string.ascii_letters) for _ in range(8))


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
user = client.users_user.create(payload={
	'id': udm_attrs['username'],
	'props': udm_attrs,
}).result()
print('New user: {!r}\n'.format(user))
user = client.users_user.get(id=udm_attrs['username']).result()
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

# MODIFY
print('Old unixhome of user {!r} is {!r}.'.format(user.props.username, user.props.unixhome))
modification = {'props': {'unixhome': '{}2'.format(user.props.unixhome)}}
user = client.users_user.modify(id=user.props.username, payload=modification).result()
print('New unixhome of user {!r} is {!r}.'.format(user.props.username, user.props.unixhome))

# DELETE
result = client.users_user.delete(id=user.props.username).result()
print('Result of deleting user {!r} is {!r} (no exception was raised).'.format(user.props.username, result))

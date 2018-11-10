# -*- coding: utf-8 -*-
#
# Copyright 2018 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

"""
Univention Directory Manager Modules (UDM) API

This is a simplified API for accessing UDM objects.
It consists of UDM modules and UDM object.
UDM modules are factories for UDM objects.
UDM objects manipulate LDAP objects.

Usage:

from univention.udm import UDM

user_mod = UDM.admin().get('users/user')
or
user_mod = UDM.machine().get('users/user')
or
user_mod = UDM.credentials('myuser', 's3cr3t').get('users/user')

obj = user_mod.get(dn)
obj.props.firstname = 'foo'  # modify property
obj.position = 'cn=users,cn=example,dc=com'  # move LDAP object
obj.save()  # apply changes

obj = user_mod.get(dn)
obj.delete()

obj = user_mod.new()
obj.props.username = 'bar'
obj.save().refresh()  # reload obj.props from LDAP after save()

for obj in UDM.machine().get('users/user').search('uid=a*'):  # search() returns a generator
	print(obj.props.firstname, obj.props.lastname)

A shortcut exists to get a UDM object directly::

	UDM.admin().obj_by_dn(dn)

The API is versioned. A fixed version must be hard coded in your code. Supply
it as argument to the UDM module factory or via :py:meth:`version()`::

	UDM.admin().version(1)  # use API version 1
	UDM.credentials('myuser', 'secret').version(2).obj_by_dn(dn)  # get object using API version 2
"""

from __future__ import absolute_import, unicode_literals
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
from bravado.exception import HTTPNotFound, HTTPUnauthorized
from .udm import UDM
from .base_http import BaseHttpModule
from .exceptions import ApiVersionMustNotChange, ApiVersionNotSupported, ConnectionError, UnknownModuleType


class UDM_HTTP(UDM):
	"""
	Dynamic factory for creating :py:class:`BaseModule` objects.

	user_mod = UDM_HTTP.credentials('myuser', 's3cr3t').get('users/user')
	"""

	@classmethod
	def admin(cls):
		"""
		Use a cn=admin connection.

		:return: a :py:class:`UDM` instance
		:rtype: UDM
		:raises ConnectionError: Non-master systems, server down, etc.
		"""
		return UDM.admin()

	@classmethod
	def machine(cls):
		"""
		Use a machine connection.

		:return: a :py:class:`UDM` instance
		:rtype: UDM
		:raises ConnectionError: File permissions, server down, etc.
		"""
		return UDM.machine()

	@classmethod
	def credentials(
			cls,
			identity,
			password,
			server,
			port=None,
	):
		"""
		Use the provided credentials to open an LDAP connection.

		`identity` must be either a username or a DN. If it is a username, a
		machine connection is used to retrieve the DN it belongs to.

		:param str identity: the username (not DN) for the HTTP connection
		:param str password: password for HTTP connection
		:param str server: HTTP server address as FQDN
		:param int port: optional HTTP server port (defaults to 443)
		:return: a :py:class:`UDM_HTTP` instance
		:rtype: UDM
		:raises ConnectionError: Invalid credentials, server down, etc.
		"""
		http_client = RequestsClient()
		port = port or 80  # TODO: 443
		scheme = 'http'  # TODO: https
		path = '/udm/swagger.json'
		swagger_spec_url = '{}://{}:{}{}'.format(scheme, server, port, path)
		http_client.set_basic_auth(server, identity, password)
		config = {'use_models': False, 'include_missing_properties': False}
		try:
			swagger_client = SwaggerClient.from_url(swagger_spec_url, http_client=http_client, config=config)
		except HTTPNotFound:
			raise ConnectionError('Could not download Swagger spec from {!r}.'.format(swagger_spec_url))
		# TODO: query to check credentials early
		return cls(swagger_client)

	def version(self, api_version):
		"""
		Set the version of the API that the UDM modules must support.

		Use in a chain of methods to get a UDM module::

			UDM_HTTP.credentials(..).version(1).get('groups/group')

		:param int api_version: load only UDM modules that support the
			specified version
		:return: self (the :py:class:`UDM` instance)
		:rtype UDM
		:raises ApiVersionMustNotChange: if called twice
		:raises ApiVersionNotSupported: if the module for `name` could not be
			loaded in that version (currently everything != 1)
		"""
		if not isinstance(api_version, int):
			raise ApiVersionNotSupported("Argument 'api_version' must be an int.", requested_version=api_version)
		if self._api_version is None:
			# TODO: query to get supported API versions
			if api_version != 1:
				raise ApiVersionNotSupported("Only api_version 1 ist supported.", requested_version=api_version)
			self._api_version = api_version
		else:
			raise ApiVersionMustNotChange()
		return self

	def get(self, name):
		"""
		Get an object of :py:class:`BaseHttpModule` (or of a subclass) for UDM
		module `name`.

		:param str name: UDM module name (e.g. `users/user`)
		:return: object of a subclass of :py:class:`BaseHttpModule`
		:rtype: BaseHttpModule
		"""
		if not hasattr(self.connection, name.replace('/', '_')):
			raise UnknownModuleType('Unknown module: {!r}.'.format(name), module_name=name)

		return BaseHttpModule(name, self.connection, self.api_version)

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
Base classes for (simplified) UDM_HTTP modules and objects.
"""

from __future__ import absolute_import, unicode_literals
import re
import sys
import copy
import datetime
from collections import namedtuple
import urllib
import urlparse
from six import string_types
from bravado.exception import HTTPNotFound, HTTPUnauthorized
from .exceptions import ConnectionError, DeletedError, NoObject, NotYetSavedError
from .base import BaseModule, BaseModuleMetadata, BaseObject, BaseObjectProperties

try:
	from typing import Any, Dict, Optional, Text, Union
except ImportError:
	pass


LdapMapping = namedtuple('LdapMapping', ('ldap2udm', 'udm2ldap'))


def serialize_obj(obj):
	"""Recursive JSON compatible serialization."""
	if any(isinstance(obj, x) for x in (bool, float, int, long, string_types)):
		# non-iterable base type
		return obj
	elif isinstance(obj, datetime.date):
		return obj.strftime('%Y-%m-%d')
	elif isinstance(obj, BaseHttpObject):
		return obj._baravo_object['uri']
	elif isinstance(obj, dict):
		res = {}
		for k, v in obj.iteritems():
			if str(k).startswith('_'):
				continue
			res[k] = serialize_obj(v)
		return res
	elif any(isinstance(obj, x) for x in (list, tuple)):
		return [serialize_obj(v) for v in obj]
	else:
		raise ValueError('Dont know how to handle type {!r} of object {!r}.'.format(type(obj), obj))


class BaseHttpObjectProperties(BaseObjectProperties):
	"""Container for UDM properties."""
	def _to_dict(self):  # type: () -> Dict[Text, Any]
		return dict((k, serialize_obj(v)) for k, v in self.__dict__.iteritems() if not str(k).startswith('_'))


class BaseHttpObject(BaseObject):
	"""
	Base class for UDM_HTTP object classes.

	Usage:
	* Creation of instances :py:class:`BaseHttpObject` is always done through a
	:py:class:`BaseHttpModul` instances py:meth:`new()`, py:meth:`get()` or
	py:meth:`search()` methods.
	* Modify an object:
		user.props.firstname = 'Peter'
		user.props.lastname = 'Pan'
		user.save()
	* Move an object:
		user.position = 'cn=users,ou=Company,dc=example,dc=com'
		user.save()
	* Delete an object:
		obj.delete()

	After saving a :py:class:`BaseHttpObject`, it is :py:meth:`reload()`ed
	automtically because UDM hooks and listener modules often add, modify or
	remove properties when saving to LDAP. As this involves LDAP, it can be
	disabled if the object is not used afterwards and performance is an issue:
		user_mod.meta.auto_reload = False
	"""
	udm_prop_class = BaseHttpObjectProperties
	_uri_regex = re.compile(r'^(https{0,1}?)://(.+?)/udm/(\w+?)/(\w+?)/(.*)')

	def __init__(self):
		"""
		Don't instantiate a :py:class:`BaseHttpObject` directly. Use
		:py:meth:`BaseHttpModule.get()`, :py:meth:`BaseHttpModule.new()` or
		:py:meth:`BaseHttpModule.search()`.
		"""
		super(BaseHttpObject, self).__init__()
		self.id = ''
		self._baravo_object = None  # type: Dict[Text, Any]
		self._fresh = True
		self._deleted = False

	def reload(self):
		"""
		Refresh object from LDAP.

		:return: self
		:rtype: BaseHttpObject
		"""
		if self._deleted:
			raise DeletedError('{} has been deleted.'.format(self), dn=self.dn, module_name=self._udm_module.name)
		if not self.dn or not self._baravo_object:
			raise NotYetSavedError(module_name=self._udm_module.name)
		self._baravo_object = self._udm_module._get_bravado_object(self.id)
		self._copy_from_bravado_obj(self._udm_module._uri2obj_cache)
		self._udm_module._uri2obj_cache.clear()
		return self

	def save(self):
		"""
		Save object to LDAP.

		:return: self
		:rtype: BaseHttpObject
		:raises MoveError: when a move operation fails
		"""
		if self._deleted:
			raise DeletedError('{} has been deleted.'.format(self), dn=self.dn, module_name=self._udm_module.name)
		if not self._fresh:
			print('WARNING: Saving stale UDM object instance')
		diff_dict = {}
		old_obj = serialize_obj(self._baravo_object)
		new_obj = self.to_dict()
		for k, v in new_obj.iteritems():
			if k in ('id', 'dn'):
				continue
			elif k == 'props':
				for prop, value in v.iteritems():
					if value != old_obj['props'][prop]:
						diff_dict.setdefault('props', {})[prop] = value
			else:
				if v != old_obj[k]:
					if k == 'options':
						# TODO: contact bravado project
						print('WARN: there is a bug in bravado, "options" will not be sent correctly.')
					diff_dict[k] = v

		mod = self._udm_module.connection.users_user
		if self.id:
			new_baravo_obj = mod.modify(id=self.id, payload=diff_dict).result()
		else:
			new_baravo_obj = mod.create(payload=diff_dict).result()
		self.id = new_baravo_obj['id']
		self.dn = new_baravo_obj['dn']
		self._fresh = False
		if self._udm_module.meta.auto_reload:
			self.reload()
		return self

	def delete(self):
		"""
		Remove the object from the LDAP database.

		:return: None
		"""
		if self._deleted:
			print('WARNING {} has already been deleted'.format(self))
			return
		if not self.dn or not self._baravo_object:
			raise NotYetSavedError()
		self._udm_module.connection.users_user.delete(id=self.id).result()
		self._baravo_object = None
		self._deleted = True

	def _uri2obj(self, uri, uri2obj_cache):  # type: (Text, Dict[Text, BaseHttpObject]) -> Union[object, None]
		"""
		Convert a URI to a BaseHttpObject instance.

		:param str uri: a URI
		:param dict uri2obj_cache: cache of URL 2 object conversions (to
			prevent infinite recursion)
		:return: a BaseHttpObject or None if there is none at `uri`
		:rtype: BaseHttpObject or None
		"""
		# TODO: use lazy object loading
		if uri not in uri2obj_cache:
			path = urlparse.urlsplit(uri).path
			path_split = path.strip('/').split('/')
			module_name = '-'.join(path_split[1:3])
			obj_id_enc = '/'.join(path_split[3:])
			obj_id = urllib.unquote(obj_id_enc)
			try:
				bravado_mod = getattr(self._udm_module.connection, module_name)
			except AttributeError:
				print('ERROR: Swagger client does not know module {!r}.'.format(module_name))
				uri2obj_cache[uri] = uri
				return uri
			try:
				bravado_obj = bravado_mod.get(id=obj_id).result()
			except HTTPNotFound:
				# TODO: fix saml/serviceprovider resource in API server (or UDM?)
				if module_name != 'saml-serviceprovider':
					print('404 (Not Found) when loading {!r} object with ID {!r} from URI {!r}.'.format(
						module_name, obj_id, uri))
				return None
			udm_http_mod = BaseHttpModule(module_name, self._udm_module.connection, self._udm_module.meta.used_api_version)
			res = udm_http_mod._load_obj(obj_id, None, bravado_obj, uri2obj_cache)
			uri2obj_cache[uri] = res
		return uri2obj_cache[uri]

	def _copy_from_bravado_obj(self, uri2obj_cache):  # type: (Dict[Text, BaseHttpObject]) -> None
		"""
		Copy UDM property values from bravado result object to `props`
		container as well as its `policies` and `options`.

		:param dict uri2obj_cache: cache of URL 2 object conversions (to
			prevent infinite recursion)
		:return: None
		"""
		self.id = self._baravo_object['id']
		self.dn = self._baravo_object['dn']
		self.options = copy.deepcopy(self._baravo_object['options'])
		self.policies = copy.deepcopy(self._baravo_object['policies'])
		self.props = self.udm_prop_class(self)
		for k, v in self._baravo_object['props'].items():
			if isinstance(v, string_types) and self._uri_regex.match(v):
				v = self._uri2obj(v, uri2obj_cache)
			elif (
					isinstance(v, list) and
					all(isinstance(x, string_types) for x in v) and
					all(self._uri_regex.match(x) for x in v)
			):
				v = [self._uri2obj(x, uri2obj_cache) for x in v]
				v = [x for x in v if x]
			setattr(self.props, k, v)
		self.superordinate = self._baravo_object['superordinate']  # type: Text
		if self.superordinate:
			self.superordinate = self._uri2obj(self.superordinate, uri2obj_cache)
		self.position = self._baravo_object['position']
		self._fresh = True

	def to_dict(self):  # type: () -> Dict[Text, Any]
		return {
			'id': self.id,
			'dn': self.dn,
			'options': self.options,
			'policies': serialize_obj(self.policies),
			'position': self.position,
			'props': self.props._to_dict(),
			'superordinate': self.superordinate,
		}


class BaseHttpModuleMetadata(BaseModuleMetadata):
	"""Base class for UDM_HTTP module meta data."""

	@property
	def identifying_property(self):
		"""
		UDM Property of which the mapped LDAP attribute is used as first
		component in a DN, e.g. `username` (LDAP attribute `uid`) or `name`
		(LDAP attribute `cn`).
		"""
		raise NotImplementedError()

	def lookup_filter(self, filter_s=None):
		"""
		Filter the UDM module uses to find its corresponding LDAP objects.

		This can be used in two ways:

		* get the filter to find all objects:
			`myfilter_s = obj.meta.lookup_filter()`
		* get the filter to find a subset of the corresponding LDAP objects
			(`filter_s` will be combined with `&` to the filter for all
			objects):
			`myfilter = obj.meta.lookup_filter('(|(givenName=A*)(givenName=B*))')`

		:param str filter_s: optional LDAP filter expression
		:return: an LDAP filter string
		:rtype: str
		"""
		raise NotImplementedError()

	@property
	def mapping(self):
		"""
		UDM properties to LDAP attributes mapping and vice versa.

		:return: a namedtuple containing two mappings: a) from UDM property to
			LDAP attribute and b) from LDAP attribute to UDM property
		:rtype: LdapMapping
		"""
		raise NotImplementedError()


class BaseHttpModule(BaseModule):
	"""
	Base class for UDM_HTTP module classes. UDM modules are basically UDM object
	factories.

	Usage:
	0. Get module using
		user_mod = UDM.admin/machine/credentials().get('users/user')
	1 Create fresh, not yet saved BaseHttpObject:
		new_user = user_mod.new()
	2 Load an existing object:
		group = group_mod.get('cn=test,cn=groups,dc=example,dc=com')
		group = group_mod.get_by_id('Domain Users')
	3 Search and load existing objects:
		dc_slaves = dc_slave_mod.search(filter_s='cn=s10*')
		campus_groups = group_mod.search(base='ou=campus,dc=example,dc=com')
	4. Load existing object(s) without `open()`ing them;
		user_mod.meta.auto_open = False
		user = user_mod.get(dn)
		user.props.groups == []
	"""
	_udm_object_class = BaseHttpObject
	_udm_module_meta_class = BaseHttpModuleMetadata
	_uri2obj_cache = {}  # type: Dict[Text, BaseHttpObject]

	class Meta:
		supported_api_versions = (1,)
		suitable_for = ['*/*']

	def __init__(self, name, connection, api_version):
		super(BaseHttpModule, self).__init__(name, connection, api_version)
		self._mod = getattr(self.connection, name)

	def new(self, superordinate=None):
		"""
		Create a new, unsaved BaseHttpObject object.

		:param superordinate: DN or UDM object this one references as its
			superordinate (required by some modules)
		:type superordinate: str or GenericObject
		:return: a new, unsaved BaseHttpObject object
		:rtype: BaseHttpObject
		"""
		# TODO: support superordinate
		res = self._load_obj(',', superordinate)
		self._uri2obj_cache.clear()
		return res

	def get(self, id):
		"""
		Load UDM object from LDAP.

		:param str id: ID of the object to load
		:return: an existing BaseHttpObject object
		:rtype: BaseHttpObject
		:raises NoObject: if no object is found at `dn`
		:raises WrongObjectType: if the object found at `dn` is not of type :py:attr:`self.name`
		"""
		res = self._load_obj(id)
		self._uri2obj_cache.clear()
		return res

	def get_by_id(self, id):
		"""
		Load UDM object from HTTP by searching for its ID.

		This is the same as :py:meth:`get()`.

		:param str id: ID of the object to load (e.g. username (uid) for users/user,
			name (cn) for groups/group etc.)
		:return: an existing BaseHttpObject object
		:rtype: BaseHttpObject
		:raises NoObject: if no object is found at `dn`
		:raises WrongObjectType: if the object found at `dn` is not of type :py:attr:`self.name`
		"""
		return self.get(id)

	def search(self, filter_s='', base='', scope='sub'):
		"""
		Get all UDM objects from LDAP that match the given filter.

		:param str filter_s: LDAP filter (only object selector like uid=foo
			required, objectClasses will be set by the UDM module)
		:param str base:
		:param str scope:
		:return: iterator of BaseHttpObject objects
		:rtype: Iterator(BaseHttpObject)
		"""
		objs = self._mod.list(_request_options={'headers': {'filter': filter_s, 'base': base, 'scope': scope}}).result()
		for obj in objs:
			yield self._load_obj(obj['id'], baravo_object=obj, uri2obj_cache=self._uri2obj_cache)
		self._uri2obj_cache.clear()

	def _get_bravado_object(self, id, superordinate=None):  # type: (Text, Optional[Text]) -> object
		"""
		Retrieve UDM object from HTTP server.

		May raise from NoObject if no object is found for `id`.

		:param str id: the id of the object to load
		:param superordinate: DN or UDM object this one references as its
			superordinate (required by some modules)
		:type superordinate: URI or GenericObject
		:return: a bravado object
		:rtype: object
		:raises NoObject: if no object is found for `id`
		"""
		# TODO: support superordinate
		try:
			return self._mod.get(id=id).result()
		except HTTPNotFound:
			raise NoObject, NoObject('No {!r} object found for ID {!r}.'.format(self.name, id), dn=id, module_name=self.name), sys.exc_info()[2]
		except HTTPUnauthorized:
			raise ConnectionError, ConnectionError('Credentials invalid or no permissions to read object {!r} with ID {!r}.'.format(self.name, id)), sys.exc_info()[2]

	def _load_obj(self, id, superordinate=None, baravo_object=None, uri2obj_cache=None):
		# type: (Text, Optional[Text], Optional[object], Optional[Dict[Text, BaseHttpObject]]) -> BaseHttpObject
		"""
		BaseHttpObject factory.

		:param str id: the id of the UDM object to load, if '' a new one
		:param superordinate: DN or UDM object this one references as its
			superordinate (required by some modules)
		:type superordinate: URI or BaseHttpObject
		:param baravo_object: baravo object instance, if unset one will be
			loaded over HTTP using `id`
		:param dict uri2obj_cache: cache of URL 2 object conversions (to
			prevent infinite recursion), if unset
			:py:attr:`self._uri2obj_cache` will be used
		:return: a BaseHttpObject
		:rtype: BaseHttpObject
		:raises NoObject: if no object is found for `id`
		"""
		obj = self._udm_object_class()
		obj._udm_module = self
		obj._baravo_object = baravo_object or self._get_bravado_object(id, superordinate)
		self._uri2obj_cache[obj._baravo_object['uri']] = obj
		if uri2obj_cache:
			uri2obj_cache[obj._baravo_object['uri']] = obj
		obj.props = obj.udm_prop_class(obj)
		obj._copy_from_bravado_obj(uri2obj_cache or self._uri2obj_cache)
		return obj

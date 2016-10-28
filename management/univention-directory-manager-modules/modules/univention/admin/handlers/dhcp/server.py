# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for the DHCP server
#
# Copyright 2004-2016 Univention GmbH
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
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

from ldap.filter import filter_format

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization

translation = univention.admin.localization.translation('univention.admin.handlers.dhcp')
_ = translation.translate

module = 'dhcp/server'
operations = ['add', 'edit', 'remove', 'search']
superordinate = 'dhcp/service'
childs = 0
usewizard = 1
short_description = _('DHCP: Server')
long_description = ''
options = {
}

property_descriptions = {
	'server': univention.admin.property(
		short_description=_('Server name'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=True,
		identifies=True
	),
}

layout = [
	Tab(_('General'), _('General settings'), layout=[
		Group(_('DHCP server description'), layout=[
			'server'
		]),
	])
]

mapping = univention.admin.mapping.mapping()
mapping.register('server', 'cn', None, univention.admin.mapping.ListToString)

from .__common import add_dhcp_options

add_dhcp_options(property_descriptions, mapping, layout)


class object(univention.admin.handlers.simpleLdap):
	module = module

	def _ldap_addlist(self):
		searchBase = self.position.getDomain()
		if self.lo.searchDn(base=searchBase, filter=filter_format('(&(objectClass=dhcpServer)(cn=%s))', [self.info['server']])):
			raise univention.admin.uexceptions.dhcpServerAlreadyUsed(self.info['server'])

		return [
			('objectClass', ['top', 'dhcpServer']),
			('dhcpServiceDN', self.superordinate.dn),
		]

	def _ldap_post_move(self, olddn):
		'''edit dhcpServiceDN'''
		oldServiceDN = self.lo.getAttr(self.dn, 'dhcpServiceDN')
		module = univention.admin.modules.identifyOne(self.position.getDn(), self.lo.get(self.position.getDn()))
		object = univention.admin.objects.get(module, None, self.lo, self.position, dn=self.position.getDn())
		shadow_module, shadow_object = univention.admin.objects.shadow(self.lo, module, object, self.position)
		self.lo.modify(self.dn, [('dhcpServiceDN', oldServiceDN[0], shadow_object.dn)])


def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=False, required=False, timeout=-1, sizelimit=0):

	filter = univention.admin.filter.conjunction('&', [univention.admin.filter.expression('objectClass', 'dhcpServer')])

	if superordinate:
		filter.expressions.append(univention.admin.filter.expression('dhcpServiceDN', superordinate.dn))

	if filter_s:
		filter_p = univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res = []
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append((object(co, lo, None, dn=dn, superordinate=superordinate, attributes=attrs)))
	return res


def identify(dn, attr):

	return 'dhcpServer' in attr.get('objectClass', [])

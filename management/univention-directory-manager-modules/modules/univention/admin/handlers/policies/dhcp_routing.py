# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin policy for the DHCP routing
#
# Copyright 2004-2019 Univention GmbH
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

from univention.admin.layout import Tab, Group
import univention.admin.syntax
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization

from univention.admin.policy import (
	register_policy_mapping, policy_object_tab,
	requiredObjectClassesProperty, prohibitedObjectClassesProperty,
	fixedAttributesProperty, emptyAttributesProperty, ldapFilterProperty
)


translation = univention.admin.localization.translation('univention.admin.handlers.policies')
_ = translation.translate


class dhcp_routingFixedAttributes(univention.admin.syntax.select):
	name = 'dhcp_routingFixedAttributes'
	choices = [
		('univentionDhcpRouters', _('Routers'))
	]


module = 'policies/dhcp_routing'
operations = ['add', 'edit', 'remove', 'search']

policy_oc = "univentionPolicyDhcpRouting"
policy_apply_to = ["dhcp/host", "dhcp/pool", "dhcp/service", "dhcp/subnet", "dhcp/sharedsubnet", "dhcp/shared"]
policy_position_dn_prefix = "cn=routing,cn=dhcp"
policies_group = "dhcp"
childs = 0
short_description = _('Policy: DHCP routing')
object_name = _('DHCP routing policy')
object_name_plural = _('DHCP routing policies')
policy_short_description = _('Routing')
long_description = ''
options = {
	'default': univention.admin.option(
		default=True,
		objectClasses=['top', 'univentionPolicy', 'univentionPolicyDhcpRouting'],
	),
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Name'),
		long_description='',
		syntax=univention.admin.syntax.policyName,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=False,
		identifies=True,
	),
	'routers': univention.admin.property(
		short_description=_('Routers'),
		long_description='',
		syntax=univention.admin.syntax.hostOrIP,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
}
property_descriptions.update(dict([
	requiredObjectClassesProperty(),
	prohibitedObjectClassesProperty(),
	fixedAttributesProperty(syntax=dhcp_routingFixedAttributes),
	emptyAttributesProperty(syntax=dhcp_routingFixedAttributes),
	ldapFilterProperty(),
]))

layout = [
	Tab(_('General'), _('DHCP routing'), layout=[
		Group(_('General DHCP routing settings'), layout=[
			'name',
			'routers',
		]),
	]),
	policy_object_tab()
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('routers', 'univentionDhcpRouters')
register_policy_mapping(mapping)


class object(univention.admin.handlers.simplePolicy):
	module = module


lookup = object.lookup


def identify(dn, attr, canonical=0):
	return 'univentionPolicyDhcpRouting' in attr.get('objectClass', [])

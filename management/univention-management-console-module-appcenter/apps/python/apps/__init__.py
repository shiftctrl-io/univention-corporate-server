#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: software management
#
# Copyright 2013 Univention GmbH
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

# standard library
import locale

# univention
from univention.lib.package_manager import PackageManager
from univention.management.console.log import MODULE
from univention.management.console.modules.decorators import simple_response, sanitize
from univention.management.console.modules.sanitizers import StringSanitizer
import univention.config_registry
import univention.management.console as umc
import univention.management.console.modules as umcm
from univention.management.console.modules.appcenter.app_center import Application, LICENSE

_ = umc.Translation('univention-management-console-module-apps').translate

class Instance(umcm.Base):
	def init(self):
		self.ucr = univention.config_registry.ConfigRegistry()
		self.ucr.load()
		self.package_manager = PackageManager(
			info_handler=MODULE.process,
			step_handler=None,
			error_handler=MODULE.warn,
			lock=False,
			always_noninteractive=True,
		)
		# in order to set the correct locale for Application
		locale.setlocale(locale.LC_ALL, str(self.locale))

	@sanitize(application=StringSanitizer(minimum=1, required=True))
	@simple_response
	def get(self, application):
		LICENSE.reload()
		application = Application.find(application)
		return application.to_dict(self.package_manager)


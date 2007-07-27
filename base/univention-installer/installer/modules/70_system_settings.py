#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Univention Installer
#  installer module: system configuration
#
# Copyright (C) 2004, 2005, 2006, 2007 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# Binary versions of this file provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

#
# Results of previous modules are placed in self.all_results (dictionary)
# Results of this module need to be stored in the dictionary self.result (variablename:value[,value1,value2])
#

import objects
from objects import *
from local import _
import string

class object(content):
	def checkname(self):
		return ['local_repository','create_home_share', 'security_profile']


	def modvars(self):
		return ['local_repository','create_home_share', 'security_profile']

	def mod_depends(self):
		return {'system_role': ['domaincontroller_master', 'domaincontroller_backup','domaincontroller_slave','memberserver','basesystem'] }

	def depends(self):
		return {}

 	def mapping(self,value):
		if value in ['normal','Normal']:
			return 'normal'
		elif value in ['strict','Strict']:
			return 'strict'
		elif value in ['open','Open']:
			return 'open'

	def profile_complete(self):
		if self.check('local_repository') | self.check('create_home_share') | self.check('security_profile'):
			return False
		return True

	def layout(self):
		self.reset_layout()
		if self.all_results.has_key('system_role') and self.all_results['system_role'] in ['domaincontroller_master', 'domaincontroller_backup' ]:
			self.elements.append(checkbox({_('Create local repository'): 'local_repository'}, self.minY+1, self.minX+2,30,1,[0]))#2
		else:
			self.elements.append(checkbox({_('Create local repository'): 'local_repository'}, self.minY+1, self.minX+2,30,1,[]))#2
		if self.all_results.has_key('system_role') and self.all_results['system_role'] in ['domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver' ]:
			self.elements.append(checkbox({_('Create home share'): 'create_home_share'}, self.minY+3, self.minX+2,30,1,[0]))#3
		elif not (self.all_results.has_key('system_role') and self.all_results['system_role'] in ['basesystem']):
			self.elements.append(checkbox({_('Create home share'): 'create_home_share'}, self.minY+3, self.minX+2,30,1,[ ]))#3

		self.add_elem('security_profile_label', textline(_('Security profile:'), self.minY, self.minX+2))

		dict={}
		dict['Normal']=['normal',0]
		dict['Strict']=['strict',1]
		dict['Open']=['open',2]

		list=['normal','strict','open']
		select=0
#		if self.all_results.has_key('security_profile'):
#			select=list.index(self.mapping(self.all_results['security_profile']))
		self.add_elem('security_profile_radio', radiobutton(dict,self.minY+1,self.minX+2,40,10,[select]))
		self.get_elem('security_profile_radio').current = select

	def input(self,key):
		if key in [ 10, 32 ] and self.btn_next():
			return 'next'
		elif key in [ 10, 32 ] and self.btn_back():
			return 'prev'
		else:
			return self.get_elem_by_id(self.current).key_event(key)

	def incomplete(self):
		return 0

	def helptext(self):
		return _('System-Settings  \n \n Various system settings')

	def modheader(self):
		return _('System-Settings')

	def result(self):
		result={}
		if len(self.elements[2].selected) > 0:
			result['local_repository']='true'
		else:
			result['local_repository']='false'
		if not (self.all_results.has_key('system_role') and self.all_results['system_role'] in ['basesystem']):
			if len(self.elements[3].selected) > 0:
				result['create_home_share']='true'
			else:
				result['create_home_share']='false'
		else:
			result['create_home_share']='false'

		result['security_profile'] = 'foo'

		return result

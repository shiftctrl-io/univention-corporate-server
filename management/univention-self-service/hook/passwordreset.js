/*
 * Copyright 2015-2017 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define*/
define([
	'dojo/topic',
	'umc/menu',
	'umc/tools',
	"login/dialog",
	"dojox/html/entities",
	'umc/i18n!'
], function(topic, menu, tools, loginDialog, entities, _) {
	function isSelfServiceURL() {
		return window.location.pathname.indexOf('/univention/self-service/') === 0;
	}

	function gotoPage(subPage) {
		if (isSelfServiceURL()) {
			window.location.hash = '#page=' + subPage;
		} else {
			// open a new tab
			window.open('/univention/self-service/' + window.location.search + '#page=' + subPage);
		}
	}

	menu.addEntry({
		parentMenuId: 'umcMenuUserSettings',
		label: _('Protect your account'),
		priority: -10,
		onClick: function() {
			gotoPage('setcontactinformation');
		}
	});
	var passwordResetEntry = menu.addEntry({
		parentMenuId: 'umcMenuUserSettings',
		priority: -5,
		label: _('Forgot your password?'),
		onClick: function() {
			gotoPage('passwordreset');
		}
	});

	topic.subscribe('/umc/authenticated', function() {
		// user has logged in -> hide menu entry
		menu.hideEntry(passwordResetEntry);
	});
	topic.subscribe('/umc/unauthenticated', function() {
		// user has logged out -> show menu entry
		menu.showEntry(passwordResetEntry);
	});

	loginDialog.addLink('<a target="_blank" href="/univention/self-service/">' + entities.encode(_('Forgot your password?')) + '</a>');
});


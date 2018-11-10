from __future__ import absolute_import, unicode_literals
import logging
from univention.config_registry import ConfigRegistry

try:
	from typing import Any, Dict, List, Optional, Text, Tuple
	import flask.app.Flask
except ImportError:
	pass


LOG_MESSAGE_FORMAT ='%(asctime)s %(levelname)-7s %(module)s.%(funcName)s:%(lineno)d  %(message)s'
LOG_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

ucr = ConfigRegistry()
ucr.load()
_logger = None


def setup_logging(app):  # type: (flask.app.Flask) -> logging.Logger
	global _logger
	if not _logger:
		flask_rp_logger = logging.getLogger('flask_restplus')
		gunicorn_logger = logging.getLogger('gunicorn')
		udm_logger = logging.getLogger('univention')
		for handler in app.logger.handlers:
			handler.setLevel(logging.DEBUG)
			handler.setFormatter(logging.Formatter(LOG_MESSAGE_FORMAT, LOG_DATETIME_FORMAT))
			flask_rp_logger.addHandler(handler)
			gunicorn_logger.addHandler(handler)
			udm_logger.addHandler(handler)
		app.logger.setLevel(logging.DEBUG)
		flask_rp_logger.setLevel(logging.DEBUG)
		gunicorn_logger.setLevel(logging.DEBUG)
		udm_logger.setLevel(logging.DEBUG)
		_logger = app.logger
	return _logger


def udm_module_name2resource_name(udm_module_name):  # type: (Text) -> Text
	return udm_module_name.replace('/', '_')


def resource_name2endpoint(resource_name):  # type: (Text) -> Text
	return 'api.{}_udm_resource'.format(resource_name)


def udm_module_name2endpoint(udm_module_name):  # type: (Text) -> Text
	return resource_name2endpoint(udm_module_name2resource_name(udm_module_name))


def get_identifying_property(mod):  # type: (GenericObject) -> Tuple[Text, Text]
	if mod.name == 'mail/folder':
		# handle Bug #48031
		identifying_udm_property = 'name'
		identifying_ldap_attribute = 'cn'
	elif mod.name == 'settings/office365profile':
		# handle Bug #48032
		identifying_udm_property = 'name'
		identifying_ldap_attribute = 'office365ProfileName'
	else:
		identifying_udm_property = mod.meta.identifying_property
		identifying_ldap_attribute = mod.meta.mapping.udm2ldap[identifying_udm_property]
	return identifying_ldap_attribute, identifying_udm_property

# Copyright 2017 Mycroft AI, Inc.
#
# This file is part of Mycroft Core.
#
# Mycroft Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mycroft Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mycroft Core.  If not, see <http://www.gnu.org/licenses/>.

"""
    This module provides the SkillSettings dictionary, which is a simple
    extension of the python dict to enable storing.

    Example:
        from mycroft.skill.settings import SkillSettings

        s = SkillSettings('./settings.json')
        s['meaning of life'] = 42
        s['flower pot sayings'] = 'Not again...'
        s.store()
"""

import json
from threading import Timer

from os.path import isfile, join

from mycroft.api import DeviceApi
from mycroft.util.log import LOG
from mycroft import MYCROFT_ROOT_PATH
from mycroft.configuration import ConfigurationManager

skills_config = ConfigurationManager.instance().get("skills")
config_dir = skills_config.get("directory", "default")
if config_dir == "default":
    SKILLS_DIR = join(MYCROFT_ROOT_PATH, "jarbas_skills")
else:
    SKILLS_DIR = config_dir


# TODO: allow deleting skill when skill is deleted
class SkillSettings(dict):
    """
        SkillSettings creates a dictionary that can easily be stored
        to file, serialized as json. It also syncs to the backend for
        skill settings

        Args:
            settings_file (str): Path to storage file
    """
    def __init__(self, directory, autopath=True):
        super(SkillSettings, self).__init__()
        self.api = DeviceApi()
        self._device_identity = self.api.identity.uuid
        # set file paths
        if autopath:
            self._settings_path = join(directory, 'settings.json')
        else:
            self._settings_path = directory
        self._meta_path = join(directory, 'settingsmeta.json')
        self._api_path = "/" + self._device_identity + "/skill"

        self.loaded_hash = hash(str(self))

        # if settingsmeta.json exists
        if isfile(self._meta_path):
            self.settings_meta = self._load_settings_meta()
            self.settings = self._get_settings()
            self._send_settings_meta()
            # start polling timer
            Timer(60, self._poll_skill_settings).start()

        self.load_skill_settings()

    @property
    def _is_stored(self):
        return hash(str(self)) == self.loaded_hash

    def __getitem__(self, key):
        return super(SkillSettings, self).__getitem__(key)

    def __setitem__(self, key, value):
        """
            Add/Update key.
        """
        return super(SkillSettings, self).__setitem__(key, value)

    def _load_settings_meta(self):
        with open(self._meta_path) as f:
            data = json.load(f)
        return data

    def _skill_exist_in_backend(self):
        """
            see if skill settings already exist in the backend
        """
        skill_identity = self._get_skill_identity()
        for skill_setting in self.settings:
            if skill_identity == skill_setting["identifier"]:
                return True
        return False

    def _send_settings_meta(self):
        """
            send settingsmeta.json to the backend if skill doesn't
            already exist
        """
        try:
            if self._skill_exist_in_backend() is False:
                response = self._put_metadata(self.settings_meta)
        except Exception as e:
            LOG.error(e)

    def _poll_skill_settings(self):
        """
            If identifier exists for this skill poll to backend to
            request settings and store it if it changes
            TODO: implement as websocket
        """
        if self._skill_exist_in_backend():
            try:
                # update settings
                self.settings = self._get_settings()
                skill_identity = self._get_skill_identity()
                for skill_setting in self.settings:
                    if skill_setting['identifier'] == skill_identity:
                        sections = skill_setting['skillMetadata']['sections']
                        for section in sections:
                            for field in section["fields"]:
                                self.__setitem__(field["name"], field["value"])

                # store value if settings has changed from backend
                self.store()

            except Exception as e:
                LOG.error(e)

            # poll backend every 60 seconds for new settings
            Timer(60, self._poll_skill_settings).start()

    def _get_skill_identity(self):
        """
            returns the skill identifier
        """
        try:
            return self.settings_meta["identifier"]
        except Exception as e:
            LOG.error(e)
            return None

    def load_skill_settings(self):
        """
            If settings.json exist, open and read stored values into self
        """
        if isfile(self._settings_path):
            with open(self._settings_path) as f:
                try:
                    json_data = json.load(f)
                    for key in json_data:
                        self.__setitem__(key, json_data[key])
                except Exception as e:
                    # TODO: Show error on webUI.  Dev will have to fix
                    # metadata to be able to edit later.
                    LOG.error(e)

    def _get_settings(self):
        """
            Get skill settings for this device from backend
        """
        return self.api.request({
            "method": "GET",
            "path": self._api_path
        })

    def _put_metadata(self, settings_meta):
        """
            PUT settingsmeta to backend to be configured in home.mycroft.ai.
            used in plcae of POST and PATCH
        """
        return self.api.request({
            "method": "PUT",
            "path": self._api_path,
            "json": settings_meta
        })

    def store(self, force=False):
        """
            Store dictionary to file if a change has occured.

            Args:
                force:  Force write despite no change
        """
        if force or not self._is_stored:
            with open(self._settings_path, 'w') as f:
                json.dump(self, f)
            self.loaded_hash = hash(str(self))

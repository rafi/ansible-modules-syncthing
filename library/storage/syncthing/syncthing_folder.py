#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018, Rafael Bodill <justrafi at gmail>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: syncthing_folder

short_description: Manage Syncthing folders

version_added: "2.7"

description:
    - "This is my longer description explaining my sample module"

options:
    id:
        description:
            - This is the unique id of this new folder
        required: true
    label:
        description:
            - The label for this new folder
        required: false
    path:
        description:
            - This is the path of the folder
        required: false
    devices:
        description:
            - List of devices to share folder with
        required: false
    host:
        description:
            - Host to connect to, including port
        default: http://127.0.0.1:8384
    api_key:
        description:
            - API key to use for authentication with host.
              If not provided, will try to auto-configure from filesystem.
        required: false
    timeout:
        description:
            - The socket level timeout in seconds
        default: 30
    state:
        description:
            - Use present/absent to ensure folder is shared, or not.
        default: present
        choices: ['absent', 'present', 'paused']

author:
    - Rafael Bodill (@rafi)
'''

EXAMPLES = '''
# Add a folder to synchronize with another device
- name: Add syncthing folder
  syncthing_folder:
    id: box
    path: ~/box
    devices:
      - 1234-1234-1234-1234
'''

RETURN = '''
response:
    description: The API response, in-case of an error.
    type: dict
'''

import os
import json
import platform
from xml.etree.ElementTree import parse

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url, url_argument_spec

SYNCTHING_API_URI = "/rest/system/config"
if platform.system() == 'Windows':
    DEFAULT_ST_CONFIG_LOCATION = '%localappdata%/Syncthing/config.xml'
elif platform.system() == 'Darwin':
    DEFAULT_ST_CONFIG_LOCATION = '$HOME/Library/Application Support/Syncthing/config.xml'
else:
    DEFAULT_ST_CONFIG_LOCATION = '$HOME/.config/syncthing/config.xml'


def make_headers(host, api_key):
    url = '{}{}'.format(host, SYNCTHING_API_URI)
    headers = {'X-Api-Key': api_key }
    return url, headers

def get_key_from_filesystem(module):
    try:
        stconfigfile = os.path.expandvars(DEFAULT_ST_CONFIG_LOCATION)
        stconfig = parse(stconfigfile)
        root = stconfig.getroot()
        gui = root.find('gui')
        api_key = gui.find('apikey').text
        return api_key
    except Exception:
        module.fail_json(msg="Auto-configuration failed. Please specify"
                             "the API key manually.")

# Fetch Syncthing configuration
def get_config(module):
    url, headers = make_headers(module.params['host'], module.params['api_key'])
    resp, info = fetch_url(
        module, url, data=None, headers=headers,
        method='GET', timeout=module.params['timeout'])

    if not info or info['status'] != 200:
        result['response'] = info
        module.fail_json(msg='Error occured while calling host', **result)

    try:
        content = resp.read()
    except AttributeError:
        result['content'] = info.pop('body', '')
        result['response'] = str(info)
        module.fail_json(msg='Error occured while reading response', **result)

    return json.loads(content)

# Post the new configuration to Syncthing API
def post_config(module, config, result):
    url, headers = make_headers(module.params['host'], module.params['api_key'])
    headers['Content-Type'] = 'application/json'

    result['msg'] = config
    resp, info = fetch_url(
        module, url, data=json.dumps(config), headers=headers,
        method='POST', timeout=module.params['timeout'])

    if not info or info['status'] != 200:
        result['response'] = str(info)
        module.fail_json(msg='Error occured while posting new config', **result)

# Returns an object of a new folder
def create_folder(params):
    folder = {
        'autoNormalize': True,
        'copiers': 0,
        'devices': [],
        'disableSparseFiles': False,
        'disableTempIndexes': False,
        'filesystemType': 'basic',
        'fsWatcherDelayS': 10,
        'fsWatcherEnabled': True,
        'hashers': 0,
        'id': params['id'],
        'ignoreDelete': False,
        'ignorePerms': False,
        'label': params['label'] if params['label'] else params['id'],
        'markerName': '.stfolder',
        'maxConflicts': -1,
        'minDiskFree': {
            'unit': '%',
            'value': 1
        },
        'order': 'random',
        'path': params['path'],
        'paused': True if params['state'] == 'paused' else False,
        'pullerMaxPendingKiB': 0,
        'pullerPauseS': 0,
        'rescanIntervalS': 3600,
        'scanProgressIntervalS': 0,
        'type': 'sendreceive',
        'useLargeBlocks': False,
        'versioning': {
            'params': {},
            'type': ''
        },
        'weakHashThresholdPct': 25
    }

    # Collect wanted devices to share folder with
    for device_id in params['devices']:
        folder['devices'].append({
            'deviceID': device_id,
            'introducedBy': '',
        })

    return folder

def run_module():
    # module arguments
    module_args = url_argument_spec()
    module_args.update(dict(
        id=dict(type='str', required=True),
        label=dict(type='str', required=False),
        path=dict(type='path', required=False),
        devices=dict(type='list', required=False, default=False),
        host=dict(type='str', default='http://127.0.0.1:8384'),
        api_key=dict(type='str', required=False, no_log=True),
        timeout=dict(type='int', default=30),
        state=dict(type='str', default='present',
                   choices=['absent', 'present', 'pause']),
    ))

    # seed the result dict in the object
    result = {
        "changed": False,
        "response": None,
    }

    # the AnsibleModule object will be our abstraction working with Ansible
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if module.params['state'] != 'absent' and not module.params['path']:
        module.fail_json(msg='You must provide a path when creating', **result)

    if module.check_mode:
        return result

    # Auto-configuration: Try to fetch API key from filesystem
    if not module.params['api_key']:
        module.params['api_key'] = get_key_from_filesystem(module)

    config = get_config(module)
    if module.params['state'] == 'absent':
        # Remove folder from list, if found
        for idx, folder in enumerate(config['folders']):
            if folder['id'] == module.params['id']:
                config['folders'].pop(idx)
                result['changed'] = True
                break
    else:
        # Bail-out if folder is already added
        for folder in config['folders']:
            if folder['id'] == module.params['id']:
                want_pause = module.params['state'] == 'pause'
                if (want_pause and folder['paused']) or \
                        (not want_pause and not folder['paused']):
                    module.exit_json(**result)
                else:
                    folder['paused'] = want_pause
                    result['changed'] = True
                    break

        # Append the new folder into configuration
        if not result['changed']:
            folder = create_folder(module.params)
            config['folders'].append(folder)
            result['changed'] = True

    if result['changed']:
        post_config(module, config, result)

    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()

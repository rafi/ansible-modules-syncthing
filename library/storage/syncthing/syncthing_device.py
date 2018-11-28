#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018, Rafael Bodill <justrafi at google mail>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: syncthing_device

short_description: Manage Syncthing devices

version_added: "2.7"

description:
    - "This is my longer description explaining my sample module"

options:
    id:
        description:
            - This is the unique id of this new device
        required: true
    name:
        description:
            - The name for this new device
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
            - Use present/absent to ensure device is added, or not.
        default: present
        choices: ['absent', 'present', 'paused']

author:
    - Rafael Bodill (@rafi)
'''

EXAMPLES = '''
# Add a device to share with
- name: Add syncthing device
  syncthing_device:
    id: 1234-1234-1234-1234
    name: my-server-name
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

# Returns an object of a new device
def create_device(params):
    device = {
        'addresses': [
            'dynamic'
        ],
        'allowedNetworks': [],
        'autoAcceptFolders': False,
        'certName': '',
        'compression': 'metadata',
        'deviceID': params['id'],
        'ignoredFolders': [],
        'introducedBy': '',
        'introducer': False,
        'maxRecvKbps': 0,
        'maxSendKbps': 0,
        'name': params['name'],
        'paused': True if params['state'] == 'paused' else False,
        'pendingFolders': [],
        'skipIntroductionRemovals': False
    }
    return device

def run_module():
    # module arguments
    module_args = url_argument_spec()
    module_args.update(dict(
        id=dict(type='str', required=True),
        name=dict(type='str', required=False),
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

    if module.params['state'] != 'absent' and not module.params['name']:
        module.fail_json(msg='You must provide a name when creating', **result)

    if module.check_mode:
        return result

    # Auto-configuration: Try to fetch API key from filesystem
    if not module.params['api_key']:
        module.params['api_key'] = get_key_from_filesystem(module)

    config = get_config(module)
    if module.params['state'] == 'absent':
        # Remove device from list, if found
        for idx, device in enumerate(config['devices']):
            if device['deviceID'] == module.params['id']:
                config['devices'].pop(idx)
                result['changed'] = True
                break
    else:
        # Bail-out if device is already added
        for device in config['devices']:
            if device['deviceID'] == module.params['id']:
                want_pause = module.params['state'] == 'pause'
                if (want_pause and device['paused']) or \
                        (not want_pause and not device['paused']):
                    module.exit_json(**result)
                else:
                    device['paused'] = want_pause
                    result['changed'] = True
                    break

        # Append the new device into configuration
        if not result['changed']:
            device = create_device(module.params)
            config['devices'].append(device)
            result['changed'] = True

    if result['changed']:
        post_config(module, config, result)

    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()

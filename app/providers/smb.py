PROVIDER = {
    'type_id': 'smb',
    'name': 'SMB / CIFS',
    'fields': {
        'host': {'label': '主机地址', 'required': True, 'type': 'text'},
        'user': {'label': '用户名', 'required': False, 'type': 'text'},
        'pass': {'label': '密码', 'required': False, 'type': 'password'},
        'domain': {'label': '域', 'required': False, 'type': 'text'},
    },
}

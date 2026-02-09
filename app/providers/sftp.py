PROVIDER = {
    'type_id': 'sftp',
    'name': 'SFTP',
    'fields': {
        'host': {'label': '主机地址', 'required': True, 'type': 'text'},
        'port': {'label': '端口', 'required': False, 'type': 'number', 'default': 22},
        'user': {'label': '用户名', 'required': True, 'type': 'text'},
        'pass': {'label': '密码', 'required': False, 'type': 'password'},
        'key_file': {'label': 'SSH 密钥文件', 'required': False, 'type': 'file'},
    },
}

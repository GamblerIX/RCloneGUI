PROVIDER = {
    'type_id': 'ftp',
    'name': 'FTP',
    'fields': {
        'host': {'label': '主机地址', 'required': True, 'type': 'text'},
        'port': {'label': '端口', 'required': False, 'type': 'number', 'default': 21},
        'user': {'label': '用户名', 'required': False, 'type': 'text'},
        'pass': {'label': '密码', 'required': False, 'type': 'password'},
        'tls': {'label': '启用 TLS', 'required': False, 'type': 'bool'},
    },
}

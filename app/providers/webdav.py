PROVIDER = {
    'type_id': 'webdav',
    'name': 'WebDAV',
    'fields': {
        'url': {'label': 'URL', 'required': True, 'type': 'text'},
        'vendor': {'label': '服务商', 'required': False, 'type': 'choice',
                   'choices': ['123Pan', 'Alipan', 'other']},
        'user': {'label': '用户名', 'required': False, 'type': 'text'},
        'pass': {'label': '密码', 'required': False, 'type': 'password'},
    },
    'vendor_config': {
        '123Pan': {
            'url': {
                'placeholder': 'https://webdav.123pan.cn/webdav',
                'fixed_url': 'https://webdav.123pan.cn/webdav',
                'readonly': True,
            },
            'user': {
                'required': True,
                'placeholder': '123云盘账号（手机号）',
            },
        },
        'Alipan': {
            'url': {
                'placeholder': 'https://openapi.alipan.com/dav',
                'fixed_url': 'https://openapi.alipan.com/dav',
                'readonly': True,
            },
            'user': {
                'required': True,
                'placeholder': '阿里云盘 WebDAV 账号',
            },
        },
        'other': {
            'url': {
                'placeholder': 'https://example.com/dav/',
            },
            'user': {
                'required': False,
                'placeholder': '',
            },
        },
    },
}

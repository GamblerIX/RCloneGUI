PROVIDER = {
    'type_id': 's3',
    'name': 'Amazon S3',
    'fields': {
        'provider': {'label': '服务商', 'required': True, 'type': 'choice',
                     'choices': ['AWS', 'Alibaba', 'Ceph', 'DigitalOcean', 'Minio', 'Other']},
        'access_key_id': {'label': '访问密钥 ID', 'required': True, 'type': 'text'},
        'secret_access_key': {'label': '访问密钥', 'required': True, 'type': 'password'},
        'region': {'label': '区域', 'required': False, 'type': 'text'},
        'endpoint': {'label': '端点', 'required': False, 'type': 'text'},
    },
    'provider_config': {
        'AWS': {
            'region': {
                'type': 'choice',
                'choices': [
                    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
                    'af-south-1', 'ap-east-1', 'ap-south-1', 'ap-south-2',
                    'ap-southeast-1', 'ap-southeast-2', 'ap-southeast-3',
                    'ap-northeast-1', 'ap-northeast-2', 'ap-northeast-3',
                    'ca-central-1', 'eu-central-1', 'eu-west-1', 'eu-west-2',
                    'eu-west-3', 'eu-south-1', 'eu-north-1',
                    'me-south-1', 'sa-east-1',
                ],
                'default': 'us-east-1',
                'required': True,
            },
            'endpoint': {
                'visible': True,
                'readonly': True,
                'auto_format': 's3.{region}.amazonaws.com',
            },
        },
        'Alibaba': {
            'region': {
                'type': 'choice',
                'choices': [
                    'oss-cn-hangzhou', 'oss-cn-shanghai', 'oss-cn-qingdao',
                    'oss-cn-beijing', 'oss-cn-shenzhen', 'oss-cn-hongkong',
                    'oss-cn-chengdu', 'oss-cn-zhangjiakou',
                    'oss-us-west-1', 'oss-us-east-1',
                    'oss-ap-southeast-1', 'oss-ap-southeast-2',
                    'oss-ap-southeast-3', 'oss-ap-southeast-5',
                    'oss-ap-northeast-1', 'oss-ap-south-1',
                    'oss-eu-central-1', 'oss-eu-west-1',
                ],
                'default': 'oss-cn-hangzhou',
                'required': True,
            },
            'endpoint': {
                'visible': True,
                'readonly': True,
                'auto_format': '{region}.aliyuncs.com',
            },
        },
        'Ceph': {
            'region': {
                'type': 'text',
                'required': False,
                'placeholder': '留空使用默认',
            },
            'endpoint': {
                'visible': True,
                'required': True,
                'placeholder': 'https://ceph.example.com',
            },
        },
        'DigitalOcean': {
            'region': {
                'type': 'choice',
                'choices': [
                    'nyc3', 'ams3', 'sgp1', 'sfo3', 'fra1', 'syd1',
                ],
                'default': 'nyc3',
                'required': True,
            },
            'endpoint': {
                'visible': True,
                'readonly': True,
                'auto_format': '{region}.digitaloceanspaces.com',
            },
        },
        'Minio': {
            'region': {
                'type': 'text',
                'required': False,
                'placeholder': '留空使用默认',
            },
            'endpoint': {
                'visible': True,
                'required': True,
                'placeholder': 'http://localhost:9000',
            },
        },
        'Other': {
            'region': {
                'type': 'text',
                'required': False,
                'placeholder': '按服务商要求填写',
            },
            'endpoint': {
                'visible': True,
                'required': True,
                'placeholder': 'https://s3.example.com',
            },
        },
    },
}

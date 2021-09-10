class StringBundle:
    DEFAULT_LOCALE = 'ru-RU'

    def __init__(self, locale=None):
        self.locale = locale if locale is not None else self.DEFAULT_LOCALE
        self.id_to_message = {}
        path = f'resources/string-{self.locale}.properties'
        self.__load_bundle(path)

    def get_string(self, string_id):
        assert (string_id in self.id_to_message), "Missing string id : " + string_id
        return self.id_to_message[string_id]

    def __load_bundle(self, path):
        PROP_SEPERATOR = '='
        with open(path, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                key_value = line.split(PROP_SEPERATOR)
                key = key_value[0].strip()
                value = PROP_SEPERATOR.join(key_value[1:]).strip().strip('"')
                self.id_to_message[key] = value

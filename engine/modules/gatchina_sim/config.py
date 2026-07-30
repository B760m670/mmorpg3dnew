# Модуль собирается на всех платформах, включая iOS: внутри только математика
# и мост к движку, ничего платформенного.
def can_build(env, platform):
    return True


def configure(env):
    pass


def get_doc_classes():
    return ["ShallowWater"]


def get_doc_path():
    return "doc_classes"

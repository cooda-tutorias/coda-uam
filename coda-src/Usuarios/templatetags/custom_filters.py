from django import template

register = template.Library()

@register.filter
def get_item(dictionary:dict, key):
    return dictionary.get(key)

@register.filter
def has_role(user, role):
    """Permite usar {{ user|has_role:"TUT" }} en templates"""
    return user.has_role(role)

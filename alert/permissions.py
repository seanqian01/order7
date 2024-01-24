from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        # 允许所有人读取
        if request.method in permissions.SAFE_METHODS:
            return True

        # 只有对象的所有者才能修改
        return obj.stra_creater == request.user

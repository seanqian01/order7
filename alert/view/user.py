from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.views import TokenObtainPairView


class LoginView(TokenObtainPairView):

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        # 自定义登录成功之后返回的结果
        result = serializer.validated_data
        result['token'] = result.pop('access')
        # result['refresh_token'] = serializer.refresh_token
        result['user_type'] = serializer.user.user_type
        result['email'] = serializer.user.email
        result['username'] = serializer.user.username
        result['telephone'] = serializer.user.telephone

        return Response(result, status=status.HTTP_200_OK)


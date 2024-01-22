from rest_framework.decorators import api_view
from .models import Strategy
from .serializers import StrategySerializer
from rest_framework.response import Response
from rest_framework import status


# 策略管理
@api_view(['GET', 'POST'])
def strategy_list(request):
    if request.method == 'GET':
        strategies = Strategy.objects.all()
        serializer = StrategySerializer(instance=strategies, many=True)
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = StrategySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(stra_creater=request.user)
            return Response(data=serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def strategy_detail(request, pk):
    try:
        strategy = Strategy.objects.get(pk=pk)
    except Strategy.DoesNotExist:
        return Response(data={'msg': '没有找到这个策略.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = StrategySerializer(strategy)
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        serializer = StrategySerializer(strategy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(data=serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        strategy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

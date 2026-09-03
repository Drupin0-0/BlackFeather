from django.shortcuts import render
from .serializers import UserSerializer
from rest_framework import status
from rest_framework.views import APIView
# Create your views here.


class RegisterView(APIView):
    def RegisterView(APIView):
        def post(self, request):
            serializer = UserSerializer(data=request.data)

            if serializer.is_valid():
                return 

from rest_framework import serializers
from .models import User, UserProfile, Technology


class TechnologySerializer(serializers.ModelSerializer):
    class Meta:
        model = Technology
        fields = ['id', 'name', 'category']


class UserProfileSerializer(serializers.ModelSerializer):
    skills = TechnologySerializer(many=True, read_only=True)

    skills_ids = serializers.PrimaryKeyRelatedField(
        queryset=Technology.objects.all(),
        many=True,
        write_only=True,
        source='skills',
        required=False
    )

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'name',
            'bio',
            'birth_date',
            'skills',
            'skills_ids'
        ]


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={
            'input_type': 'password',
            'placeholder': 'Password'
        }
    )

    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'password',
            'profile'
        ]
    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
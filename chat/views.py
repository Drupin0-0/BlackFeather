
from django.shortcuts import get_object_or_404, render

from Tasks.models import Project


def test_chat(request, project_code):
    project = get_object_or_404(
        Project,
        code=project_code
    )

    return render(
        request,
        "test.html",
        {
            "project": project,
            "project_code": project.code,
        }
    )
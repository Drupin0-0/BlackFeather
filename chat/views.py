from django.shortcuts import render


def test_chat(request, project_id):
    return render(
        request,
        "test.html",
        {
            "project_id": project_id,
        }
    )
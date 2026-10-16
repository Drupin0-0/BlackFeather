from django.urls import path

from . import views

urlpatterns = [
    path('', views.project_notes_view, name='project_notes'),
    path('api/tree/', views.notes_tree_view, name='project_notes_tree'),
    path('api/sections/create/', views.section_create, name='notes_section_create'),
    path('api/sections/<int:section_id>/rename/', views.section_rename, name='notes_section_rename'),
    path('api/sections/<int:section_id>/delete/', views.section_delete, name='notes_section_delete'),
    path('api/sections/<int:section_id>/reorder/', views.section_reorder, name='notes_section_reorder'),
    path('api/sections/<int:section_id>/visibility/', views.section_visibility_update, name='notes_section_visibility'),
    path('api/sections/<int:section_id>/subsections/create/', views.subsection_create, name='notes_subsection_create'),
    path('api/subsections/<int:subsection_id>/rename/', views.subsection_rename, name='notes_subsection_rename'),
    path('api/subsections/<int:subsection_id>/delete/', views.subsection_delete, name='notes_subsection_delete'),
    path('api/subsections/<int:subsection_id>/reorder/', views.subsection_reorder, name='notes_subsection_reorder'),
    path('api/subsections/<int:subsection_id>/pages/create/', views.page_create, name='notes_page_create'),
    path('api/pages/<int:page_id>/', views.page_content_view, name='notes_page_content'),
    path('api/pages/<int:page_id>/version/', views.page_version_view, name='notes_page_version'),
    path('api/pages/<int:page_id>/rename/', views.page_rename, name='notes_page_rename'),
    path('api/pages/<int:page_id>/delete/', views.page_delete, name='notes_page_delete'),
    path('api/pages/<int:page_id>/reorder/', views.page_reorder, name='notes_page_reorder'),
]

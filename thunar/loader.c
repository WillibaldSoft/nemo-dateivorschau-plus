/* SPDX-License-Identifier: GPL-3.0-or-later
 * Small resident Thunarx bootstrap. Python is global so GI can resolve its ABI.
 * No GTK/Thunar structs or private C symbols are accessed here.
 */
#include <dlfcn.h>
#include <stdio.h>
#ifndef PYTHON_SONAME
#error PYTHON_SONAME is required
#endif
#ifndef PREVIEW_PYTHON_PATH
#define PREVIEW_PYTHON_PATH "/usr/lib/nemo-dateivorschau-plus"
#endif
void thunar_extension_initialize(void *plugin) {
    void (*resident)(void *, int) = dlsym(RTLD_DEFAULT, "thunarx_provider_plugin_set_resident");
    if (resident) resident(plugin, 1);
    void *python = dlopen(PYTHON_SONAME, RTLD_NOW | RTLD_GLOBAL);
    if (!python) { fprintf(stderr, "Dateivorschau: %s\n", dlerror()); return; }
    int (*initialized)(void) = dlsym(python, "Py_IsInitialized");
    void (*initialize)(void) = dlsym(python, "Py_Initialize");
    int (*run)(const char *) = dlsym(python, "PyRun_SimpleString");
    int (*ensure)(void) = dlsym(python, "PyGILState_Ensure");
    void (*release)(int) = dlsym(python, "PyGILState_Release");
    if (!initialized || !initialize || !run || !ensure || !release) return;
    int created = !initialized();
    if (created) initialize();
    int state = ensure();
    run("import sys; sys.path = [p for p in sys.path if p]; sys.path.insert(0, '" PREVIEW_PYTHON_PATH "'); import thunar_sidebar; thunar_sidebar.start()");
#ifdef PREVIEW_INTEGRATION_TEST
    run("import os; sys.path.insert(0, os.environ['PREVIEW_TEST_DIR']); import driver");
#endif
    release(state);
    if (created) {
        void *(*save)(void) = dlsym(python, "PyEval_SaveThread");
        if (save) save();
    }
}
void thunar_extension_shutdown(void) { /* Shared interpreter belongs to process. */ }
void thunar_extension_list_types(const unsigned long **types, int *count) {
    *types = NULL; *count = 0;
}

/* Thunar exposes selected-files as a borrowed GList pointer property, which
 * GI cannot marshal. Convert it synchronously to file URIs on the GTK thread.
 * Callers pass PyGObject's native __gpointer__ capsule, never an arbitrary ID.
 */
#include <stdlib.h>
#include <string.h>
struct FileList { void *data; struct FileList *next, *prev; };
char *dateivorschau_selected_uris(void *view) {
    void (*get)(void *, const char *, ...) = dlsym(RTLD_DEFAULT, "g_object_get");
    char *(*uri)(void *) = dlsym(RTLD_DEFAULT, "thunarx_file_info_get_uri");
    void (*release)(void *) = dlsym(RTLD_DEFAULT, "g_free");
    if (!get || !uri || !release || !view) return NULL;
    struct FileList *files = NULL;
    get(view, "selected-files", &files, NULL);
    size_t size = 1;
    char *result = calloc(1, size);
    for (int n=0; files && n<256; files=files->next, n++) {
        char *value = uri(files->data);
        if (!value) continue;
        size_t len = strlen(value);
        char *expanded = realloc(result, size+len+1);
        if (!expanded) { release(value); free(result); return NULL; }
        result=expanded;
        memcpy(result+size-1,value,len);
        result[size+len-1]='\n'; result[size+len]='\0';
        size+=len+1;
        release(value);
    }
    return result;
}
void dateivorschau_free(void *value) { free(value); }

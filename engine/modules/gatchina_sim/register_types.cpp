#include "register_types.h"

#include "core/object/class_db.h"

#include "shallow_water.h"

void initialize_gatchina_sim_module(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
	GDREGISTER_CLASS(ShallowWater);
}

void uninitialize_gatchina_sim_module(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
}

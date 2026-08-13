#include "register_types.h"

#include "core/object/class_db.h"

#include "shallow_water.h"
#include "water_volume.h"

void initialize_gatchina_sim_module(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
	GDREGISTER_CLASS(ShallowWater);
	GDREGISTER_CLASS(WaterVolume);
}

void uninitialize_gatchina_sim_module(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
}

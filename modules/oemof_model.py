import oemof.solph as solph
import yaml
import os
import pandas as pd
from oemof.tools import logger
from oemof.network.graph import create_nx_graph
from oemof_visio import ESGraphRenderer
# from q100opt.plots import plot_es_graph
from matplotlib import pyplot as plt

import logging

tech_param = "parameter.yaml"
heat_load_file = "LoadProfiles_input.CSV"
temp_ambient_file = "T_amp_input.CSV"
pv_file = "PV_timeseries.csv"

# #########

with open(tech_param) as file:
    tech_param = yaml.safe_load(file)

heat_load = pd.read_csv(os.path.join("..", heat_load_file), sep=";")
total_heat_load = heat_load["E_th_RH_HH"] + heat_load["E_th_TWE_HH"] + \
                  heat_load["E_th_RH_HH"] + heat_load["E_th_TWE_HH"] + \
                  heat_load["E_th_loss"]

t_amb = pd.read_csv(os.path.join("..", temp_ambient_file), sep=";")

pv_normed_series = pd.read_csv(os.path.join(pv_file))


def create_solph_model(
        capacity_boiler=3000,
        capacity_chp_el=400,
        capacity_hp_air=1000,
        capacity_hp_ground=500,
        capacity_electrlysis_el=250,
        capacity_pv=1500,
        capacity_thermal_storage_m3=1000,
        techparam=tech_param,
):
    number_of_time_steps = 24 * 4 * 7

    # initiate the logger (see the API docs for more information)
    logger.define_logging(
        logfile="oemof_example.log",
        screen_level=logging.INFO,
        file_level=logging.DEBUG,
    )

    logging.info("Initialize the energy system")
    date_time_index = pd.date_range(
        "1/1/2012", periods=number_of_time_steps, freq="15min"
    )

    energysystem = solph.EnergySystem(timeindex=date_time_index)

    logging.info("Create oemof objects")

    b_gas = solph.Bus(label="gas")
    b_elec = solph.Bus(label="electricity")
    b_heat_generation = solph.Bus(label="heat_generation")
    b_heat_storage_out = solph.Bus(label="storage_out")
    b_heat_grid = solph.Bus(label="heat_grid")
    b_h2 = solph.Bus(label="h2")

    energysystem.add(b_gas, b_elec, b_heat_generation, b_heat_storage_out,
                     b_heat_grid, b_h2)

    gas_source = solph.Source(
        label="gas_grid",
        outputs={b_gas: solph.Flow(
            variable_costs=techparam["gas_source"]["variable_costs"],
            emission_factor=techparam["gas_source"]["emission_factor"],
        )}
    )

    elec_source = solph.Source(
        label="electricity_grid",
        outputs={b_elec: solph.Flow(
            variable_costs=techparam["electricity_source"]["variable_costs"],
            emission_factor=techparam["electricity_source"]["emission_factor"],
        )}
    )

    pv_source = solph.Source(
        label="pv",
        outputs={b_elec: solph.Flow(
            nominal_value=capacity_pv,
            fix=pv_normed_series["pv.fix"],
        )}
    )

    heat_demand = solph.Sink(
        label="demand",
        inputs={b_heat_grid: solph.Flow(
            nominal_value=1,
            fix=total_heat_load,
        )}
    )

    elec_sell = solph.Sink(
        label="elec_sell",
        inputs={b_elec: solph.Flow(
            variable_costs=techparam["electricity_sell"]["variable_costs"],
            emission_factor=techparam["electricity_sell"]["emission_factor"],
        )}
    )

    h2_sell = solph.Sink(
        label="h2_sell",
        inputs={b_h2: solph.Flow(
            variable_costs=techparam["hydrogen_sell"]["variable_costs"],
            emission_factor=techparam["hydrogen_sell"]["emission_factor"],
        )}
    )

    energysystem.add(h2_sell, elec_sell, heat_demand, pv_source, elec_source,
                     gas_source)

    boiler = solph.Transformer(
        label="gas_boiler",
        inputs={b_gas: solph.Flow()},
        outputs={b_heat_generation: solph.Flow(
            nominal_value=capacity_boiler,
            min=techparam["gas_boiler"]["minimum_load"],
            nonconvex=solph.options.NonConvex()
        )},
        conversion_factors={
            b_heat_generation: techparam["gas_boiler"]["efficiency"],
        }
    )

    chp = solph.Transformer(
        label="chp",
        inputs={b_gas: solph.Flow()},
        outputs={
            b_elec: solph.Flow(
                nominal_value=capacity_chp_el,
                min=techparam["chp"]["minimum_load"],
                nonconvex=solph.options.NonConvex()),
            b_heat_generation: solph.Flow()
        },
        conversion_factors={
            b_elec: techparam["chp"]["efficiency_el"],
            b_heat_generation: techparam["chp"]["efficiency_th"],
        }
    )

    ely = solph.Transformer(
        label="electrolysis",
        inputs={b_elec: solph.Flow(
            nominal_value=capacity_electrlysis_el,
            min=techparam["electrolysis"]["minimum_load"],
            nonconvex=solph.options.NonConvex(),
            summed_min=techparam["electrolysis"]["fullloadhours_min"],
            summed_max=techparam["electrolysis"]["fullloadhours_max"],
        )},
        outputs={
            b_h2: solph.Flow(),
            b_heat_generation: solph.Flow(),
        },
        conversion_factors={
            b_h2: techparam["electrolysis"]["efficiency_h2"],
            b_heat_generation:
                techparam["electrolysis"]["efficiency_heat_excess"],
        }
    )

    hp_air = solph.Transformer(
        label="heatpump_air",
        inputs={
            b_elec: solph.Flow(
                nominal_value=capacity_hp_air,
                min=techparam["heatpump_air"]["minimum_load"],
                nonconvex=solph.options.NonConvex(),
            )
        },
        outputs={
            b_heat_generation: solph.Flow(),
        },
        conversion_factors={
            b_heat_generation: techparam["heatpump_air"]["cop"],
        }
    )

    hp_ground = solph.Transformer(
        label="heatpump_ground",
        inputs={
            b_elec: solph.Flow(
                nominal_value=capacity_hp_ground,
                min=techparam["heatpump_ground"]["minimum_load"],
                nonconvex=solph.options.NonConvex(),
            )
        },
        outputs={
            b_heat_generation: solph.Flow(),
        },
        conversion_factors={
            b_heat_generation: techparam["heatpump_ground"]["cop"],
        }
    )

    energysystem.add(hp_air, hp_ground, chp, boiler, ely)

    storage_capa = capacity_thermal_storage_m3 * 30

    thermal_storage = solph.GenericStorage(
        label="thermal_storage",
        inputs={b_heat_generation: solph.Flow()},
        outputs={b_heat_storage_out: solph.Flow()},
        nominal_storage_capacity=storage_capa,
        loss_rate=0.0001,
        fixed_losses_relative=0.0002,
    )

    grid_pump = solph.Transformer(
        label="dhs_grid_pump",
        inputs={
            b_heat_storage_out: solph.Flow(),
            b_elec: solph.Flow(),
        },
        outputs={
            b_heat_grid: solph.Flow(),
        },
        conversion_factors={
            b_elec: 0.015,
            b_heat_storage_out: 1,
            b_heat_grid: 1,
        }
    )

    energysystem.add(grid_pump, thermal_storage)

    # plot_es_graph(energysystem, show=True)

    # gr = ESGraphRenderer(energy_system=energysystem, filepath="energy_system",
    #                      img_format="png")
    # gr.view()

    return energysystem


def solve_model(energysystem):

    solver = "gurobi"  # 'glpk', 'gurobi',....
    debug = False  # Set number_of_timesteps to 3 to get a readable lp-file.
    solver_verbose = True  # show/hide solver output

    logging.info("Optimise the energy system")

    # initialise the operational model
    model = solph.Model(energysystem)

    # This is for debugging only. It is not(!) necessary to solve the problem and
    # should be set to False to save time and disc space in normal use. For
    # debugging the timesteps should be set to 3, to increase the readability of
    # the lp-file.
    if debug:
        filename = os.path.join(
            solph.helpers.extend_basic_path("lp_files"), "basic_example.lp"
        )
        logging.info("Store lp-file in {0}.".format(filename))
        model.write(filename, io_options={"symbolic_solver_labels": True})

    # if tee_switch is true solver messages will be displayed
    logging.info("Solve the optimization problem")
    model.solve(solver=solver, solve_kwargs={"tee": solver_verbose})

    logging.info("Store the energy system with the results.")

    # The processing module of the outputlib can be used to extract the results
    # from the model transfer them into a homogeneous structured dictionary.

    # add results to the energy system to make it possible to store them.
    energysystem.results["main"] = solph.processing.results(model)
    energysystem.results["meta"] = solph.processing.meta_results(model)

    return energysystem


esys = create_solph_model()
esys = solve_model(esys)

# print and plot some results
results = esys.results["main"]

heat_gen = solph.views.node(results, "heat_generation")
heat_store = solph.views.node(results, "thermal_storage")
elec = solph.views.node(results, "electricity")

print(heat_gen["sequences"].sum())
print(heat_store["sequences"].sum())
print(elec["sequences"].sum())

fig1, ax = plt.subplots(figsize=(10, 5))
heat_gen["sequences"].plot(ax=ax)
plt.show()

fig2, ax = plt.subplots(figsize=(10, 5))
heat_store["sequences"].plot(ax=ax)
plt.show()

fig3, ax = plt.subplots(figsize=(10, 5))
elec["sequences"].plot(ax=ax)
plt.show()

logging.info("Done!")
import pandas as pd
import numpy as np
import os

filenames = ["data/results_Scenario A_ErrorProfiles_input.csv",
             "data/results_Scenario A_ErrorProfiles_input_Boiler_14_10_18.csv",
             "data/results_Scenario A_ErrorProfiles_input_CHP_13_1_18.csv",
             "data/results_Scenario B_ErrorProfiles_input.csv",
             "data/results_Scenario B_ErrorProfiles_input_Boiler_14_10_18.csv",
             "data/results_Scenario B_ErrorProfiles_input_CHP_13_1_18.csv",
             "data/results_Scenario C_ErrorProfiles_input.csv",
             "data/results_Scenario C_ErrorProfiles_input_Boiler_14_10_18.csv",
             "data/results_Scenario C_ErrorProfiles_input_CHP_13_1_18.csv"]

Tband = 5  # this is +/- 5 as a tolerance band
dTnorm = 5  # [C] # same as the Tband?
dtnorm = 3600  # [s]


def maximum_deviation(df):
    tmax = df['dx'].max()
    MD = tmax / dTnorm

    return MD


def recovery_time(df, dtnorm=dtnorm):
    tout = df.loc[df["dx"] != 0].index[0]
    tin = df.loc[df["dx"] != 0].index[-1]

    RT = (tin - tout) / dtnorm

    return RT


def performance_loss(df, dtnorm=dtnorm):
    area = df['dx'].sum()
    area_norm = dTnorm * dtnorm

    PL = area / area_norm

    return PL


def resilience_index(MD, RT, PL):
    IRI = MD * RT * PL
    RI = 1 / (1 + IRI)

    return RI


def prepare_dataframe(filename):
    df = pd.read_csv(filename)

    df["fMU_PhyModel.temperature_HeatGrid_FF.T"] = df["fMU_PhyModel.temperature_HeatGrid_FF.T"] - 273.15

    temps = df.loc[:, ["fMU_PhyModel.temperature_HeatGrid_FF.T", "controller.u_T_HeatGrid_FF_set"]]
    temps.rename(columns={'fMU_PhyModel.temperature_HeatGrid_FF.T': 'Temperature',
                          'controller.u_T_HeatGrid_FF_set': "Set Temperature"}, inplace=True)

    df = temps
    df["dT1"] = df["Set Temperature"] + Tband
    df["dT2"] = df["Set Temperature"] - Tband

    time = np.linspace(0, 900 * len(df["Temperature"]), len(df["Temperature"]), endpoint=False)
    df["Time"] = time
    df = df.set_index("Time")

    df["dx1"] = np.where((df['Temperature'] >= df["dT1"]), df['Temperature'] - df["dT1"], 0)
    df["dx2"] = np.where((df['Temperature'] <= df["dT2"]), df["dT2"] - df["Temperature"], 0)
    df["dx"] = df["dx1"] + df["dx2"]

    return df


def calculate_resilience(filenames=filenames):
    resilience_info = {}

    for filename in filenames:
        df = prepare_dataframe(filename)

        t_dis_end = df.loc[df["dx"] == df["dx"].max()].index.values[0]  # time index of max deviation point
        t_dis_start = df["dx"].ne(0).idxmax()  # first non-zero element´s time index
        dtnorm = t_dis_end - t_dis_start

        MD = maximum_deviation(df)
        RT = recovery_time(df, dtnorm=dtnorm)
        PL = performance_loss(df, dtnorm=dtnorm)
        RI = resilience_index(MD, RT, PL)

        resilience_info.update(({filename: [MD, RT, PL, RI]}))

    index = ["MD", "RT", "PL", "RI"]
    resilience = pd.DataFrame(resilience_info, index=index)
    # resilience["Average"] = resilience.mean(axis=1)

    path = os.getcwd() + "/data"
    if not os.path.isdir(path):
        os.mkdir(path)
    csv_filename = "data/resilience.csv"
    resilience.to_csv(csv_filename)

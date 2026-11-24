function p = islanding_params()
%ISLANDING_PARAMS Parameters of the critical-bus islanding model (pilot feeder F07).
%   Every value is a plain double so the struct can be used inside a Simulink MATLAB Function
%   block. Values tagged SOURCED come from config/city.yaml or a named standard; ASSUMPTION
%   marks engineering choices still to be confirmed with an inverter vendor.

% ---- time -------------------------------------------------------------------------------
p.dt      = 1e-4;      % s, fixed step (10 per millisecond; the fastest loop is 10 ms)
p.t_end   = 9.0;       % s
p.log_every = 10;      % log every 10th step (1 ms)

% ---- event timeline (a compressed outage; the stress-week outages last up to an hour) -----
p.t_trip    = 1.0;     % s, upstream feeder breaker opens (DISCOM rotation or overload trip)
p.t_pump    = 2.5;     % s, water pump starts while islanded
p.t_return  = 5.0;     % s, grid voltage is back at the feeder
p.grid_phase_on_return = 2.0;   % rad (115 deg): the returning grid is out of phase with the island

% ---- critical bus loads at 18:45 (SOURCED: config/city.yaml critical_loads_kw) -------------
p.p_clinic = 12;   p.pf_clinic = 0.95;    % kW, health sub-centre
p.p_school = 4;    p.pf_school = 0.90;    % kW, school (evening: lights, study room; 8 kW by day)
p.p_light  = 6;    p.pf_light  = 0.95;    % kW, core street lighting
p.p_pump   = 15;   p.pf_pump   = 0.85;    % kW, water pump, direct-on-line induction motor
p.pump_inrush   = 5.0;   % x rated current at start (ASSUMPTION, typical DOL 5-7x)
p.pump_inrush_pf = 0.35; % power factor during start (ASSUMPTION)
p.pump_inrush_tau = 0.25;% s, decay of the starting current (ASSUMPTION)

% ---- the rest of feeder F07 (disconnected by the island switch) -------------------------
p.p_feeder_rest = 280;   % kW at 18:45 on the stress day, homes + workshops
p.pf_feeder_rest = 0.92;

% ---- battery inverter (SOURCED: config/city.yaml battery, 200 kWh / 100 kW) ---------------
p.s_rated   = 100;     % kVA
p.s_overload = 1.1;    % short-term current limit, x rated (ASSUMPTION, 10 s rating)
p.p_dispatch = 90;     % kW the battery is discharging into the feeder at 18:45 (peak shaving)
p.tau_meas  = 0.02;    % s, power measurement filter (one cycle)
p.tau_v     = 0.01;    % s, inverter voltage loop
p.tau_p     = 0.05;    % s, power loop when following the grid
p.mp        = 0.5/100; % Hz per kW: 1 % frequency droop (0.5 Hz at rated power)
p.mq        = 0.05/100;% pu per kvar: 5 % voltage droop
p.k_sec     = 1.0;     % 1/s, secondary control: restores 50 Hz in a few seconds
p.k_sync    = 0.5;     % Hz per rad, phase-matching gain once the grid is back
p.sync_f_max = 0.3;    % Hz, largest frequency offset used for phase matching
p.sync_angle = 10*pi/180;   % rad, close the tie only within 10 deg ...
p.sync_df    = 0.1;    % Hz ... and 0.1 Hz ...
p.sync_dv    = 0.05;   % pu ... and 5 % voltage
p.sync_hold  = 0.2;    % s, for this long
p.ramp_back = 60;      % kW/s, ramp back to the dispatch after reconnection

% ---- island detection and the tie switch (IEEE 1547-2018 style; ASSUMPTION for settings) --
p.uv_detect  = 0.88;   % pu, undervoltage that signals loss of grid
p.t_detect   = 0.04;   % s, two cycles below it
p.t_switch   = 0.06;   % s, three cycles for the static switch to open the tie

% ---- grid -----------------------------------------------------------------------------------
p.f0 = 50;  p.v_grid = 1.0;

% ---- battery pack (LFP, 240 cells in series; ASSUMPTION) ---------------------------------
p.cells   = 240;   p.r_pack = 0.05;   % ohm
p.ah      = 200e3 / (240*3.2);        % Ah for 200 kWh at 768 V nominal
p.eta_inv = 0.97;
p.soc0    = 0.62;                     % evening state of charge
end

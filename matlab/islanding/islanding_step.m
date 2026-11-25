function [xn, y] = islanding_step(x, t, variant, p)
%ISLANDING_STEP One fixed step of the critical-bus islanding model.
%   [xn, y] = islanding_step(x, t, variant, p)
%   x        state vector (16x1), see ISLANDING_X0
%   t        time, s
%   variant  0 = baseline (no battery)
%            1 = GridSetu, inverter follows the grid, island switch (40 ms detect + 60 ms open)
%            2 = GridSetu, inverter always grid-forming, static switch (10 ms + 5 ms)
%   p        parameters from ISLANDING_PARAMS
%   y        [t f_hz v_pu p_inv_kw q_inv_kvar p_served_kw i_bat_a v_bat_v soc tie mode angle_deg]'
%
%   Average-value (RMS) model: the inverter is a controlled voltage source behind its control
%   loops, loads are constant impedance, the pump start is a decaying inrush current. It shows
%   the millisecond-to-second behaviour that the 15-minute simulator cannot: island detection,
%   transfer to grid-forming, frequency and voltage control, a motor start in the island and
%   synchronised reconnection. Used unchanged by the Simulink model and by ISLANDING_REFERENCE.

xn = x;
dt = p.dt;
Pm = x(1); Qm = x(2); dsec = x(3); th = x(4); V = x(5); soc = x(6);
tie = x(7); mode = x(8); uvt = x(9); swt = x(10); synct = x(11); pref = x(12);
returned = x(15);

grid_up = (t < p.t_trip) || (t >= p.t_return);

% ---- critical loads at 1 pu voltage ------------------------------------------------------
P0 = p.p_clinic + p.p_school + p.p_light;
Q0 = p.p_clinic*tan(acos(p.pf_clinic)) + p.p_school*tan(acos(p.pf_school)) + ...
     p.p_light*tan(acos(p.pf_light));
if t >= p.t_pump
    irel = 1 + (p.pump_inrush - 1)*exp(-(t - p.t_pump)/p.pump_inrush_tau);
    pf = p.pf_pump + (p.pump_inrush_pf - p.pf_pump)*(irel - 1)/(p.pump_inrush - 1);
    s_pump = p.p_pump/p.pf_pump*irel;
    P0 = P0 + s_pump*pf;
    Q0 = Q0 + s_pump*sqrt(1 - pf^2);
end

f = p.f0; p_inv = 0; q_inv = 0; served = 0;

if variant < 0.5
    % ---------------- baseline: the critical loads share the feeder's fate ----------------
    if grid_up
        V = p.v_grid; served = P0*V^2;
    else
        V = 0; f = NaN; served = 0;
    end
else
    % ---------------- GridSetu -------------------------------------------------------------
    if grid_up && returned < 0.5 && t >= p.t_return
        th = atan2(sin(th - p.grid_phase_on_return), cos(th - p.grid_phase_on_return));
        returned = 1;
    end
    if mode < 0.5
        % grid-following: the inverter injects its dispatch; the grid sets V and f
        if grid_up && tie > 0.5
            V = p.v_grid;
            step_max = p.ramp_back*dt;
            pref = pref + max(-step_max, min(step_max, p.p_dispatch - pref));
            Pm = Pm + dt/p.tau_p*(pref - Pm);
            th = 0;
            uvt = 0;
        else
            % grid gone, tie still closed: the inverter's current cannot hold up the whole
            % feeder, so the voltage collapses until the island is detected and separated
            if variant > 1.5
                % grid-forming: holds its voltage until it reaches its current limit with the
                % whole feeder hanging on it
                q_rest = p.p_feeder_rest*tan(acos(p.pf_feeder_rest));
                s_all = sqrt((P0 + p.p_feeder_rest)^2 + (Q0 + q_rest)^2);
                V = min(1, p.s_rated*p.s_overload/s_all);
                Pm = (P0 + p.p_feeder_rest)*V^2;
                t_det = p.t_detect_fast; t_sw = p.t_switch_fast;
            else
                Pm = Pm + dt/p.tau_p*(pref - Pm);
                V = min(1, sqrt(max(Pm, 0)/(P0 + p.p_feeder_rest)));
                t_det = p.t_detect; t_sw = p.t_switch;
            end
            if V < p.uv_detect
                uvt = uvt + dt;
            else
                uvt = 0;
            end
            if uvt >= t_det && swt < 0
                swt = 0;                          % trip the static switch
            end
            if swt >= 0
                swt = swt + dt;
                if swt >= t_sw                     % tie open: run the island
                    tie = 0; mode = 1; dsec = 0; synct = 0;
                    Pm = P0*V^2; Qm = Q0*V^2;      % re-initialise the measurement
                end
            end
        end
        p_inv = Pm;
        q_inv = 0;
        served = P0*V^2;
    else
        % grid-forming island: droop + secondary control, current limit, then resync
        p_load = P0*V^2; q_load = Q0*V^2;
        Pm = Pm + dt/p.tau_meas*(p_load - Pm);
        Qm = Qm + dt/p.tau_meas*(q_load - Qm);
        f_sync = 0;
        if grid_up
            e = atan2(sin(th), cos(th));
            f_sync = max(-p.sync_f_max, min(p.sync_f_max, -p.k_sync*e));
        end
        f_droop = p.f0 - p.mp*Pm + dsec;
        f = f_droop + f_sync;
        dsec = dsec + dt*p.k_sec*(p.f0 - f_droop);
        th = th + dt*2*pi*(f - p.f0);
        s0 = sqrt(P0^2 + Q0^2);                 % load apparent power at 1 pu
        v_ref = p.v_grid - p.mq*Qm;
        v_lim = p.s_rated*p.s_overload/max(s0, 1e-6);   % current limit, impedance load
        V = V + dt/p.tau_v*(min(v_ref, v_lim) - V);
        p_inv = p_load; q_inv = q_load; served = p_load;
        % synchronising check, then close the tie and hand back to the grid (bumpless)
        e = atan2(sin(th), cos(th));
        if grid_up && abs(e) < p.sync_angle && abs(f - p.f0) < p.sync_df && abs(V - p.v_grid) < p.sync_dv
            synct = synct + dt;
        else
            synct = 0;
        end
        if synct >= p.sync_hold
            tie = 1; mode = 0; th = 0; pref = Pm; uvt = 0; swt = -1;
        end
    end
end

% ---- battery pack (GridSetu only) --------------------------------------------------------
i_bat = 0; v_bat = 0;
if variant >= 0.5
    ocv = p.cells*(3.20 + 0.15*(soc - 0.5));
    if p_inv >= 0
        p_dc = 1e3*p_inv/p.eta_inv;
    else
        p_dc = 1e3*p_inv*p.eta_inv;
    end
    i_bat = (ocv - sqrt(max(ocv^2 - 4*p.r_pack*p_dc, 0)))/(2*p.r_pack);
    v_bat = ocv - p.r_pack*i_bat;
    soc = soc - i_bat*dt/3600/p.ah;
end

% ---- energy book-keeping -----------------------------------------------------------------
P0_nominal = P0;    % what the loads would draw at 1 pu
xn(13) = x(13) + served*dt/3600;
xn(14) = x(14) + max(P0_nominal - served, 0)*dt/3600;

xn(1) = Pm; xn(2) = Qm; xn(3) = dsec; xn(4) = th; xn(5) = V; xn(6) = soc;
xn(7) = tie; xn(8) = mode; xn(9) = uvt; xn(10) = swt; xn(11) = synct; xn(12) = pref;
xn(15) = returned;
xn(16) = x(16) + 1;

y = [t; f; V; p_inv; q_inv; served; i_bat; v_bat; soc; tie; mode; ...
     180/pi*atan2(sin(th), cos(th))];
end

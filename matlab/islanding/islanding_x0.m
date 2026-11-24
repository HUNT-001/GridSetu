function x0 = islanding_x0(p)
%ISLANDING_X0 Initial state of the islanding model: grid connected, battery dispatching.
%   1 Pm (kW)  2 Qm (kvar)  3 secondary correction (Hz)  4 angle to grid (rad)  5 V (pu)
%   6 SoC  7 tie closed  8 mode (0 following, 1 forming)  9 undervoltage timer (s)
%   10 switch timer (s, -1 idle)  11 sync timer (s)  12 power reference (kW)
%   13 critical energy served (kWh)  14 critical energy not served (kWh)
%   15 grid-returned flag  16 step counter
x0 = zeros(16, 1);
x0(1) = p.p_dispatch;  x0(5) = p.v_grid;  x0(6) = p.soc0;  x0(7) = 1;
x0(10) = -1;           x0(12) = p.p_dispatch;
end

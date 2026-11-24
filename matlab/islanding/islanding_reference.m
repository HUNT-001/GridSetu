function [Y, xend] = islanding_reference(variant, p)
%ISLANDING_REFERENCE Run the islanding model as a plain MATLAB loop (also runs in Octave).
%   [Y, xend] = islanding_reference(variant, p) logs one row of y every p.log_every steps,
%   exactly as the Simulink model's To Workspace block does, so the two can be compared.
if nargin < 2, p = islanding_params(); end
n = round(p.t_end/p.dt);
x = islanding_x0(p);
Y = zeros(floor(n/p.log_every) + 1, 12);
r = 0;
for k = 0:n
    t = k*p.dt;
    [xn, y] = islanding_step(x, t, variant, p);
    if mod(k, p.log_every) == 0
        r = r + 1;
        Y(r, :) = y';
    end
    x = xn;
end
Y = Y(1:r, :);
xend = x;
end

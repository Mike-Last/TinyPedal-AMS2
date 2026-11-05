# Game API feature matrix, and what it means for AMS2

Every game API in `tinypedal/adapter/` implements the same reader interface (`_reader.py`, 174 features in
12 groups). This page lists, for each feature, whether each game's reader returns game data or a fixed
placeholder (`0.0`, `-1`, empty, and so on). The table was generated from the reader source on 2026-11-05: a
feature counts as a placeholder when its method only returns a constant.

- ✅ reads data from the game
- ≈ AMS2 only: worked out from other data rather than read directly (see the note)
- — fixed placeholder, the game API does not provide it

## Summary

| | rF2 | LMU | ACC | AMS2 |
|---|:-:|:-:|:-:|:-:|
| Features with data | 147 | 163 | 125 | 126 |
| Placeholders | 27 | 11 | 49 | 48 |

AMS2 now has slightly more coverage than ACC: 126 features with data and 48 placeholders. rF2 and LMU get more because
they have a REST API and a richer shared memory plugin. Most AMS2 placeholders are also placeholders for ACC,
so the widgets that use them already cope with missing data (they show zero or blank, or fall back to a
widget setting).

Widgets only ask about other drivers (by index) for the Vehicle, Timing and Lap groups, plus raw throttle,
raw brake, fuel and tyre compound. AMS2 provides per-driver data for all of those, so the fact that AMS2 only
sends telemetry for the player's own car does not break any widget.

## AMS2 gaps filled by estimates

Both use data AMS2 already sends (checked against the game's `SharedMemory.h`, version 14). The work is
done by `DamageTracker` in `ams2_sharedmemory.py`, which updates with every shared memory sample.

| Feature | Used by | How |
|---|---|---|
| `vehicle.impact_position` | Damage widget (impact cone) | For car contact, the direction of the other car (`mLastOpponentCollisionIndex`) from the player's position and heading. For anything else, the opposite of the largest sudden velocity change (`mWorldVelocity`) in the 0.3 s before damage rises, as the car is pushed away from where it was hit. Velocity changes under 0.5 m/s between samples (about 5 g at 100 Hz) are ignored as normal driving. Both use the same position and heading conventions as the Radar widget. |
| `vehicle.damage_severity` | Damage, Damage stats | Each rise in aero damage goes to the body parts facing the impact (the part straight on gets twice the share of each neighbour). A part takes at most heavy damage (2), and any excess goes to the other parts, so the total stays at aero damage x 16 and the body integrity reading is unchanged. With no impact direction, damage is spread evenly, as before. Repairs scale every part down. Viewing another car, or a session reset, starts again from that car's damage spread evenly. |

## AMS2 gaps that could still be filled

| Feature | Used by | How | Confidence |
|---|---|---|---|
| `brake.wear` | Brake wear widget, wheels module | `mBrakeDamage` (0 to 1 per corner). The module expects remaining thickness in metres and compares it with the thickness at the start, so `(1 - damage) x nominal thickness` gives the right percentage but made-up millimetres. Check in game first that the value goes up with normal brake wear and not only in crashes. | Unverified |
| `vehicle.is_detached` | Nothing at the moment | True when any wheel's `TYRE_ATTACHED` flag is off. Easy, but no widget reads it. | High, low value |

## Possible estimates, not recommended

| Feature | Why not |
|---|---|
| `tyre.slip_angle` | `mLocalVelocity` and `mAngularVelocity` (yaw rate, not used yet) give axle slip only if you know the distance from the centre of gravity to each axle, and the front also needs the steering ratio. AMS2 provides neither. |
| `session.wetness` | No field. Building it up from rain density over time would be a guess, and the Weather widget would show it as fact. |
| `inputs.steering_range` | No field. ACC uses a table of steering lock per car; AMS2 has too many cars for that to be practical. The steering widgets already have a `manual_steering_range` setting. |
| `wheel.track_front/rear`, `wheel.wheelbase` | ACC works these out from tyre contact points; AMS2 does not send them. The Rake angle and Roll angle widgets fall back to their own settings. |
| `vehicle.pit_stop_time`, `engine.absolute_refill` | ACC estimates them from the fuel set in the pit menu; AMS2 does not send pit menu settings. |

## Not provided by AMS2

These stay as placeholders: brake compound and migration, exhaust temperature, electric motor RPM, torque,
temperatures and regeneration, virtual energy, lift and coast, force feedback, safety car position, start
lights, weather forecast, track grip, time of day and time scale, track limits points, TC cut and slip, brake
migration and anti-roll bar levels, wipers, auto clutch, tyre load and deflection, camber, toe, suspension
force, downforce, incidents, team name, repair time and car setup.

## AMS2 data that TinyPedal has nowhere to put

AMS2 sends these, but the shared reader interface has no feature for them: oil, water and fuel pressure;
clutch temperature, wear, overheating and slipping; launch control stage; the lap of the mandatory pit stop
(`mEnforcedPitStopLap`); ERS auto mode; wing settings; handbrake; odometer; crash state; nationalities;
world and personal best lap and sector times; yaw rate.

Using them means adding features to `_reader.py`, which all four readers then have to implement. That file
is upstream's, so every upstream release merge would risk a conflict and the automatic sync would stop. If
any of these are wanted, a fork-only widget that reads the AMS2 data directly keeps the change inside the
`ams2_*` files, the same way the Watchlist widget is kept separate.

## Existing AMS2 features that could be more accurate

- `timing.last_sector` is rebuilt from the player's sector splits. AMS2 also sends sector times for every
  driver (`mCurrentSector1Times` to `mCurrentSector3Times`, `mFastestSector1Times` to `mFastestSector3Times`),
  which could be read directly.
- Tyre compound is only known for the player's car; AMS2 does not send it for other drivers.

## Full table

### State

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `active` | ✅ | ✅ | ✅ | ✅ |  |
| `paused` | ✅ | ✅ | ✅ | ✅ |  |
| `resets` | ✅ | ✅ | ✅ | ✅ |  |
| `version` | ✅ | ✅ | ✅ | ✅ |  |

### Brake

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `compound_name` | — | — | ✅ | — |  |
| `bias_front` | ✅ | ✅ | ✅ | ✅ |  |
| `migration` | — | ✅ | — | — |  |
| `pressure` | ✅ | ✅ | ✅ | ≈ | from brake pedal input |
| `temperature` | ✅ | ✅ | ✅ | ✅ |  |
| `wear` | ✅ | ✅ | ✅ | — |  |

### ElectricMotor

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `state` | ✅ | ✅ | — | ≈ | boost (P2P/KERS) active |
| `battery_charge` | ✅ | ✅ | — | ≈ | boost amount remaining |
| `rpm` | ✅ | ✅ | — | — |  |
| `torque` | ✅ | ✅ | — | — |  |
| `motor_temperature` | ✅ | ✅ | — | — |  |
| `water_temperature` | ✅ | ✅ | — | — |  |
| `regeneration_level` | — | ✅ | — | — |  |

### Engine

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `gear` | ✅ | ✅ | ✅ | ✅ |  |
| `gear_max` | ✅ | ✅ | — | ✅ |  |
| `rpm` | ✅ | ✅ | ✅ | ✅ |  |
| `rpm_max` | ✅ | ✅ | ✅ | ✅ |  |
| `torque` | ✅ | ✅ | — | ✅ |  |
| `turbo` | ✅ | ✅ | — | ✅ |  |
| `oil_temperature` | ✅ | ✅ | — | ✅ |  |
| `water_temperature` | ✅ | ✅ | ✅ | ✅ |  |
| `exhaust_temperature` | — | — | ✅ | — |  |
| `lift_and_coast_progress` | — | ✅ | — | — |  |
| `fuel` | ✅ | ✅ | ✅ | ✅ |  |
| `fuel_fraction` | ✅ | ✅ | — | ✅ |  |
| `tank_capacity` | ✅ | ✅ | ✅ | ✅ |  |
| `virtual_energy` | — | ✅ | — | — |  |
| `max_virtual_energy` | — | ✅ | — | — |  |
| `absolute_refill` | ✅ | ✅ | ✅ | — |  |

### Inputs

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `throttle` | ✅ | ✅ | ✅ | ✅ |  |
| `throttle_raw` | ✅ | ✅ | ✅ | ✅ |  |
| `brake` | ✅ | ✅ | ✅ | ✅ |  |
| `brake_raw` | ✅ | ✅ | ✅ | ✅ |  |
| `clutch` | ✅ | ✅ | ✅ | ✅ |  |
| `clutch_raw` | ✅ | ✅ | ✅ | ✅ |  |
| `steering` | ✅ | ✅ | ✅ | ✅ |  |
| `steering_range` | ✅ | ✅ | ✅ | — |  |
| `force_feedback` | ✅ | ✅ | ✅ | — |  |

### Lap

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `completed` | ✅ | ✅ | ✅ | ✅ |  |
| `track_length` | ✅ | ✅ | ✅ | ✅ |  |
| `distance` | ✅ | ✅ | ✅ | ✅ |  |
| `progress` | ✅ | ✅ | ✅ | ✅ |  |
| `maximum` | ✅ | ✅ | — | ✅ |  |
| `remaining` | ✅ | ✅ | — | ✅ |  |
| `sector_index` | ✅ | ✅ | ✅ | ✅ |  |
| `safety_car_distance` | ✅ | — | — | — |  |
| `safety_car_active` | ✅ | — | — | ≈ | full course yellow state |

### Session

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `combo_name` | ✅ | ✅ | ✅ | ✅ |  |
| `track_name` | ✅ | ✅ | ✅ | ✅ |  |
| `identifier` | ✅ | ✅ | ✅ | ✅ |  |
| `elapsed` | ✅ | ✅ | ✅ | ✅ |  |
| `remaining` | ✅ | ✅ | ✅ | ✅ |  |
| `session_type` | ✅ | ✅ | ✅ | ✅ |  |
| `finish_type` | ✅ | ✅ | — | ≈ | time vs laps only |
| `in_race` | ✅ | ✅ | ✅ | ✅ |  |
| `private_qualifying` | ✅ | ✅ | — | ✅ |  |
| `pit_open` | ✅ | ✅ | — | ✅ |  |
| `pre_race` | ✅ | ✅ | ✅ | ✅ |  |
| `green_flag` | ✅ | ✅ | ✅ | ✅ |  |
| `blue_flag` | ✅ | ✅ | ✅ | ✅ |  |
| `yellow_flag` | ✅ | ✅ | ✅ | ✅ |  |
| `start_lights` | ✅ | — | — | — |  |
| `track_temperature` | ✅ | ✅ | ✅ | ✅ |  |
| `ambient_temperature` | ✅ | ✅ | ✅ | ✅ |  |
| `raininess` | ✅ | ✅ | ✅ | ✅ |  |
| `wetness` | ✅ | ✅ | ✅ | — |  |
| `weather_forecast` | ✅ | ✅ | ✅ | — |  |
| `cloud_coverage` | ✅ | ✅ | ✅ | ≈ | from rain density |
| `grip_level` | — | ✅ | ✅ | — |  |
| `track_time` | ✅ | ✅ | ✅ | — |  |
| `time_scale` | ✅ | ✅ | ✅ | — |  |
| `limits_points` | — | ✅ | — | — |  |
| `cut_points` | — | ✅ | — | — |  |
| `wind_direction` | — | — | ✅ | ✅ |  |
| `wind_speed` | — | — | ✅ | ✅ |  |

### Switch

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `tc_level` | — | ✅ | ✅ | ✅ |  |
| `tc_cut_level` | — | ✅ | ✅ | — |  |
| `tc_slip_level` | — | ✅ | — | — |  |
| `abs_level` | — | ✅ | ✅ | ✅ |  |
| `motor_map_level` | — | ✅ | ✅ | ≈ | ERS deployment mode |
| `brake_migration_level` | — | ✅ | — | — |  |
| `front_arb_level` | — | ✅ | — | — |  |
| `rear_arb_level` | — | ✅ | — | — |  |
| `wipers` | — | ✅ | ✅ | — |  |
| `headlights` | ✅ | ✅ | ✅ | ✅ |  |
| `ignition` | ✅ | ✅ | ✅ | ✅ |  |
| `speed_limiter` | ✅ | ✅ | ✅ | ✅ |  |
| `tc_active` | — | ✅ | ✅ | ✅ |  |
| `abs_active` | — | ✅ | ✅ | ✅ |  |
| `drs_status` | ✅ | ✅ | — | ✅ |  |
| `auto_clutch` | ✅ | — | ✅ | — |  |

### Timing

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `elapsed` | ✅ | ✅ | ✅ | ✅ |  |
| `is_last_valid` | ✅ | ✅ | ✅ | ≈ | fork's own tracker |
| `current_laptime` | ✅ | ✅ | ✅ | ≈ | opponents from fork's tracker |
| `last_laptime` | ✅ | ✅ | ✅ | ✅ |  |
| `best_laptime` | ✅ | ✅ | ✅ | ✅ |  |
| `reference_laptime` | ✅ | ✅ | ✅ | ✅ |  |
| `estimated_laptime` | ✅ | ✅ | ✅ | ✅ |  |
| `estimated_time_into` | ✅ | ✅ | ✅ | ✅ |  |
| `last_sector` | ✅ | ✅ | ✅ | ≈ | rebuilt from player sector splits |

### Tyre

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `compound_name` | ✅ | ✅ | ✅ | ≈ | player only |
| `compound_class` | ✅ | ✅ | ✅ | ≈ | player only |
| `surface_temperature_avg` | ✅ | ✅ | ✅ | ✅ |  |
| `surface_temperature_ico` | ✅ | ✅ | ✅ | ✅ |  |
| `inner_temperature_avg` | ✅ | ✅ | — | ✅ |  |
| `inner_temperature_ico` | ✅ | ✅ | — | ≈ | one layer temp copied to I/C/O |
| `pressure` | ✅ | ✅ | ✅ | ✅ |  |
| `load` | ✅ | ✅ | — | — |  |
| `wear` | ✅ | ✅ | — | ✅ |  |
| `puncture` | ✅ | ✅ | ✅ | ✅ |  |
| `carcass_temperature` | ✅ | ✅ | ✅ | ✅ |  |
| `vertical_deflection` | ✅ | ✅ | — | — |  |
| `slip_angle` | ✅ | ✅ | ✅ | — |  |

### Vehicle

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `incidents` | — | ✅ | ✅ | — |  |
| `is_player` | ✅ | ✅ | ✅ | ✅ |  |
| `is_driving` | ✅ | ✅ | ✅ | ✅ |  |
| `player_index` | ✅ | ✅ | ✅ | ✅ |  |
| `slot_id` | ✅ | ✅ | ✅ | ✅ |  |
| `driver_name` | ✅ | ✅ | ✅ | ✅ |  |
| `team_name` | ✅ | ✅ | ✅ | — |  |
| `vehicle_model` | ✅ | ✅ | ✅ | ✅ |  |
| `class_name` | ✅ | ✅ | ✅ | ✅ |  |
| `same_class` | ✅ | ✅ | ✅ | ✅ |  |
| `total_vehicles` | ✅ | ✅ | ✅ | ✅ |  |
| `place` | ✅ | ✅ | ✅ | ✅ |  |
| `qualification` | ✅ | ✅ | — | ≈ | grid recorded by fork's tracker |
| `in_pits` | ✅ | ✅ | ✅ | ✅ |  |
| `in_garage` | ✅ | ✅ | ✅ | ✅ |  |
| `in_paddock` | ✅ | ✅ | ✅ | ✅ |  |
| `number_pitstops` | ✅ | ✅ | ✅ | ≈ | counted by fork's tracker |
| `number_penalties` | ✅ | ✅ | ✅ | ≈ | pending drive-through/stop-go only |
| `pit_request` | ✅ | ✅ | ✅ | ✅ |  |
| `pit_stop_time` | ✅ | ✅ | ✅ | — |  |
| `repair_time` | ✅ | ✅ | — | — |  |
| `finish_state` | ✅ | ✅ | ✅ | ✅ |  |
| `orientation_yaw` | ✅ | ✅ | ✅ | ✅ |  |
| `position_xyz` | ✅ | ✅ | ✅ | ✅ |  |
| `position_longitudinal` | ✅ | ✅ | ✅ | ✅ |  |
| `position_lateral` | ✅ | ✅ | ✅ | ✅ |  |
| `position_vertical` | ✅ | ✅ | ✅ | ✅ |  |
| `acceleration_lateral` | ✅ | ✅ | ✅ | ✅ |  |
| `acceleration_longitudinal` | ✅ | ✅ | ✅ | ✅ |  |
| `acceleration_vertical` | ✅ | ✅ | ✅ | ✅ |  |
| `velocity_lateral` | ✅ | ✅ | ✅ | ✅ |  |
| `velocity_longitudinal` | ✅ | ✅ | ✅ | ✅ |  |
| `velocity_vertical` | ✅ | ✅ | ✅ | ✅ |  |
| `speed` | ✅ | ✅ | ✅ | ✅ |  |
| `downforce_front` | ✅ | ✅ | — | — |  |
| `downforce_rear` | ✅ | ✅ | — | — |  |
| `damage_severity` | ✅ | ✅ | ✅ | ≈ | aero damage spread over the parts facing each impact |
| `aero_damage` | ✅ | ✅ | — | ✅ |  |
| `integrity` | ✅ | ✅ | ✅ | ≈ | max(aero, engine damage) |
| `is_detached` | ✅ | ✅ | — | — |  |
| `impact_time` | ✅ | ✅ | ✅ | ≈ | from damage rises and opponent contact |
| `impact_position` | ✅ | ✅ | ✅ | ≈ | opponent position, or sudden velocity change |
| `setup` | ✅ | ✅ | — | — |  |

### Wheel

| Feature | rF2 | LMU | ACC | AMS2 | AMS2 note |
|---|:-:|:-:|:-:|:-:|---|
| `track_front` | — | — | ✅ | — |  |
| `track_rear` | — | — | ✅ | — |  |
| `wheelbase` | — | — | ✅ | — |  |
| `camber` | ✅ | ✅ | — | — |  |
| `toe` | ✅ | ✅ | ✅ | — |  |
| `rotation` | ✅ | ✅ | ✅ | ✅ |  |
| `ride_height` | ✅ | ✅ | — | ✅ |  |
| `third_spring_deflection` | ✅ | ✅ | ✅ | ≈ | average of corner travel |
| `suspension_deflection` | ✅ | ✅ | ✅ | ✅ |  |
| `suspension_force` | ✅ | ✅ | — | — |  |
| `suspension_damage` | ✅ | ✅ | ✅ | ✅ |  |
| `position_vertical` | ✅ | ✅ | — | ✅ |  |
| `is_detached` | ✅ | ✅ | — | ✅ |  |
| `offroad` | ✅ | ✅ | — | ✅ |  |

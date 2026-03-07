"""
Smart Grain Silo - Fan Optimization via Reinforcement Learning
===============================================================
Trains an RL agent (PPO) to learn the optimal exhaust fan control policy.

Problem:
  The ESP8266 uses a simple threshold: humidity > 50% → fan ON.
  But how LONG should the fan run? Running too long wastes electricity.
  Running too short means humidity rebounds and the fan cycles wastefully.

Solution:
  We simulate the silo environment using real historical data patterns,
  then train a Proximal Policy Optimization (PPO) agent to learn when
  to turn the fan ON/OFF to minimize:
    - Time spent above the mold threshold
    - Total electricity consumed by the fan
    - Number of rapid on/off cycles (reduces relay wear)

The trained policy can then be translated back into improved ESP8266 
threshold logic (e.g., "run fan for 8 minutes once triggered, then 
wait 5 minutes before re-evaluating").

Usage:
    python fan_optimization.py                    # Train + evaluate
    python fan_optimization.py --timesteps 100000 # Longer training
    python fan_optimization.py --evaluate-only    # Load saved model
"""

import argparse
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback

from config import (
    DATA_DIR, MODEL_DIR, PLOT_DIR,
    RL_TOTAL_TIMESTEPS, RL_HUMIDITY_TARGET,
    HUMIDITY_FAN_ON, HUMIDITY_ALERT,
)


# ════════════════════════════════════════════════════════════════
#  CUSTOM GYMNASIUM ENVIRONMENT: GRAIN SILO
# ════════════════════════════════════════════════════════════════

class GrainSiloEnv(gym.Env):
    """
    Simulates the silo micro-climate for RL training.
    
    State (observation):
        [humidity, temperature, gas_value, fan_state, time_since_last_toggle]
    
    Action (discrete):
        0 = Keep fan OFF
        1 = Turn fan ON
    
    Reward shaping:
        + Positive for keeping humidity near target
        - Penalty for humidity in mold danger zone
        - Penalty for fan energy usage (proportional to ON-time)
        - Penalty for rapid toggling (relay wear)
    """
    
    metadata = {"render_modes": []}
    
    def __init__(self, data: pd.DataFrame = None):
        super().__init__()
        
        self.action_space = spaces.Discrete(2)  # 0=OFF, 1=ON
        
        # Observation: [humidity, temp, gas, fan_on, time_since_toggle]
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([100, 60, 1023, 1, 500], dtype=np.float32),
        )
        
        # Load real data patterns for simulation
        if data is not None and len(data) > 0:
            self.real_humidity = data["humidity"].values
            self.real_temp = data["temperature"].values
            self.real_gas = data["gas_value"].values if "gas_value" in data.columns else np.zeros(len(data))
        else:
            # Fallback: generate synthetic data
            n = 5000
            self.real_humidity = 40 + 20 * np.sin(np.linspace(0, 8 * np.pi, n)) + np.random.normal(0, 3, n)
            self.real_temp = 25 + 8 * np.sin(np.linspace(0, 4 * np.pi, n)) + np.random.normal(0, 1, n)
            self.real_gas = 40 + np.random.normal(0, 10, n)
        
        self.max_steps = len(self.real_humidity) - 1
        self.reset()
    
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = 0
        self.fan_on = False
        self.time_since_toggle = 0
        self.total_fan_on_time = 0
        self.toggle_count = 0
        self.humidity = self.real_humidity[0]
        
        return self._get_obs(), {}
    
    def _get_obs(self):
        return np.array([
            np.clip(self.humidity, 0, 100),
            np.clip(self.real_temp[self.step_idx], 0, 60),
            np.clip(self.real_gas[self.step_idx], 0, 1023),
            float(self.fan_on),
            min(self.time_since_toggle, 500),
        ], dtype=np.float32)
    
    def step(self, action):
        prev_fan = self.fan_on
        self.fan_on = bool(action)
        
        # Track toggling
        if self.fan_on != prev_fan:
            self.toggle_count += 1
            self.time_since_toggle = 0
        else:
            self.time_since_toggle += 1
        
        if self.fan_on:
            self.total_fan_on_time += 1
        
        # ── Simulate humidity dynamics ──
        # Base: follow real data trends
        self.step_idx = min(self.step_idx + 1, self.max_steps)
        natural_hum = self.real_humidity[self.step_idx]
        
        # Fan effect: each step with fan ON reduces humidity by 0.3-0.8%
        # depending on current humidity (more effective at higher humidity)
        if self.fan_on:
            fan_effect = 0.3 + 0.5 * (self.humidity / 100.0)
            self.humidity = self.humidity - fan_effect
        else:
            # Humidity drifts toward natural level
            drift = (natural_hum - self.humidity) * 0.1
            self.humidity += drift
        
        # Add small noise
        self.humidity += np.random.normal(0, 0.5)
        self.humidity = np.clip(self.humidity, 10, 100)
        
        # ── Reward Calculation ──
        reward = 0.0
        
        # 1. Humidity control reward (most important)
        if self.humidity < HUMIDITY_FAN_ON:
            reward += 1.0  # Good: below fan threshold
        elif self.humidity < HUMIDITY_ALERT:
            reward -= 0.5  # Warning zone
        else:
            reward -= 2.0  # Mold danger zone — heavy penalty
        
        # 2. Bonus for being near target
        distance_to_target = abs(self.humidity - RL_HUMIDITY_TARGET)
        reward += max(0, 1.0 - distance_to_target / 20.0)
        
        # 3. Energy cost penalty
        if self.fan_on:
            reward -= 0.15  # Small constant cost for running fan
        
        # 4. Toggling penalty (relay wear)
        if self.fan_on != prev_fan:
            reward -= 0.5  # Penalize each toggle
        
        # ── Episode termination ──
        terminated = self.step_idx >= self.max_steps
        truncated = False
        
        info = {
            "humidity": self.humidity,
            "fan_on": self.fan_on,
            "total_fan_time": self.total_fan_on_time,
            "toggles": self.toggle_count,
        }
        
        return self._get_obs(), reward, terminated, truncated, info
    
    def get_metrics(self):
        """Return episode performance metrics."""
        return {
            "total_fan_on_time": self.total_fan_on_time,
            "fan_duty_cycle": self.total_fan_on_time / max(self.step_idx, 1),
            "total_toggles": self.toggle_count,
        }


# ════════════════════════════════════════════════════════════════
#  THRESHOLD BASELINE (for comparison)
# ════════════════════════════════════════════════════════════════

def run_threshold_baseline(env: GrainSiloEnv):
    """
    Run the current ESP8266 threshold policy (fan ON if hum > 50%)
    as a baseline to compare against the RL agent.
    """
    obs, _ = env.reset()
    total_reward = 0
    humidity_log = []
    fan_log = []
    
    done = False
    while not done:
        # Simple threshold: fan ON if humidity > 50%
        action = 1 if obs[0] > HUMIDITY_FAN_ON else 0
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        humidity_log.append(info["humidity"])
        fan_log.append(info["fan_on"])
        done = terminated or truncated
    
    metrics = env.get_metrics()
    return total_reward, humidity_log, fan_log, metrics


def run_rl_agent(env: GrainSiloEnv, model):
    """Run the trained RL agent on the environment."""
    obs, _ = env.reset()
    total_reward = 0
    humidity_log = []
    fan_log = []
    
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        humidity_log.append(info["humidity"])
        fan_log.append(info["fan_on"])
        done = terminated or truncated
    
    metrics = env.get_metrics()
    return total_reward, humidity_log, fan_log, metrics


# ════════════════════════════════════════════════════════════════
#  VISUALIZATION
# ════════════════════════════════════════════════════════════════

def plot_comparison(baseline_result, rl_result):
    """Compare threshold baseline vs RL agent performance."""
    b_reward, b_hum, b_fan, b_metrics = baseline_result
    r_reward, r_hum, r_fan, r_metrics = rl_result
    
    fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
    
    steps = range(len(b_hum))
    
    # ── Humidity Comparison ──
    ax = axes[0]
    ax.plot(steps, b_hum, color="#ff9800", linewidth=1, alpha=0.7, label="Threshold Policy")
    ax.plot(steps, r_hum, color="#2196f3", linewidth=1, alpha=0.7, label="RL Agent")
    ax.axhline(y=HUMIDITY_FAN_ON, color="red", linestyle="--", alpha=0.5, label=f"Fan Threshold ({HUMIDITY_FAN_ON}%)")
    ax.axhline(y=RL_HUMIDITY_TARGET, color="green", linestyle=":", alpha=0.5, label=f"Target ({RL_HUMIDITY_TARGET}%)")
    ax.set_ylabel("Humidity (%)")
    ax.set_title("Humidity Control: Threshold vs RL Agent", fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # ── Fan State Comparison ──
    ax = axes[1]
    ax.fill_between(steps, 0, [int(f) for f in b_fan], color="#ff9800", alpha=0.3, step="post", label="Threshold Fan")
    ax.fill_between(steps, 0, [int(f) + 1.2 for f in r_fan], color="#2196f3", alpha=0.3, step="post", label="RL Fan (offset)")
    ax.set_ylabel("Fan State")
    ax.set_title("Fan Actuation Pattern", fontweight="bold")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["OFF", "ON"])
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # ── Cumulative Reward ──
    ax = axes[2]
    b_cum = np.cumsum([0] * len(b_hum))  # We'll compute per-step rewards
    r_cum = np.cumsum([0] * len(r_hum))
    ax.text(0.5, 0.5, 
            f"PERFORMANCE SUMMARY\n\n"
            f"{'Metric':<25} {'Threshold':>12} {'RL Agent':>12}\n"
            f"{'─'*50}\n"
            f"{'Total Reward':<25} {b_reward:>12.1f} {r_reward:>12.1f}\n"
            f"{'Fan Duty Cycle':<25} {b_metrics['fan_duty_cycle']:>11.1%} {r_metrics['fan_duty_cycle']:>11.1%}\n"
            f"{'Total Toggles':<25} {b_metrics['total_toggles']:>12d} {r_metrics['total_toggles']:>12d}\n"
            f"{'Fan ON Steps':<25} {b_metrics['total_fan_on_time']:>12d} {r_metrics['total_fan_on_time']:>12d}\n"
            f"{'Energy Savings':<25} {'baseline':>12} {max(0, (1 - r_metrics['fan_duty_cycle'] / max(b_metrics['fan_duty_cycle'], 0.001)) * 100):>11.1f}%",
            transform=ax.transAxes,
            fontfamily="monospace", fontsize=11,
            verticalalignment="center", horizontalalignment="center",
            bbox=dict(boxstyle="round", facecolor="#f5f5f5", edgecolor="#ccc"))
    ax.set_axis_off()
    
    plt.suptitle("Smart Grain Silo — RL Fan Optimization Results",
                 fontsize=15, fontweight="bold", y=1.01)
    plt.tight_layout()
    
    out_path = os.path.join(PLOT_DIR, "rl_fan_optimization.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [+] Plot saved: {out_path}")


# ════════════════════════════════════════════════════════════════
#  POLICY EXTRACTION (translate RL → ESP8266 rules)
# ════════════════════════════════════════════════════════════════

def extract_policy_rules(env: GrainSiloEnv, model):
    """
    Run the RL agent across many scenarios and extract simple rules
    that can be hard-coded back into the ESP8266.
    """
    print(f"\n{'='*60}")
    print("  EXTRACTED POLICY RULES")
    print(f"{'='*60}")
    
    # Test: at what humidity does the agent turn the fan on?
    fan_on_thresholds = []
    fan_off_thresholds = []
    
    for temp_test in [20, 25, 30, 35]:
        for hum_test in range(30, 90):
            # Test with fan currently OFF
            obs_off = np.array([hum_test, temp_test, 50, 0, 50], dtype=np.float32)
            action_off, _ = model.predict(obs_off, deterministic=True)
            if action_off == 1:
                fan_on_thresholds.append((temp_test, hum_test))
                break
        
        for hum_test in range(90, 30, -1):
            # Test with fan currently ON
            obs_on = np.array([hum_test, temp_test, 50, 1, 50], dtype=np.float32)
            action_on, _ = model.predict(obs_on, deterministic=True)
            if action_on == 0:
                fan_off_thresholds.append((temp_test, hum_test))
                break
    
    print("\n  Fan ON thresholds (when fan is OFF, agent turns ON at):")
    for temp, hum in fan_on_thresholds:
        print(f"    Temp={temp}°C → Fan ON at Humidity={hum}%")
    
    print("\n  Fan OFF thresholds (when fan is ON, agent turns OFF at):")
    for temp, hum in fan_off_thresholds:
        print(f"    Temp={temp}°C → Fan OFF at Humidity={hum}%")
    
    if fan_on_thresholds and fan_off_thresholds:
        avg_on = np.mean([h for _, h in fan_on_thresholds])
        avg_off = np.mean([h for _, h in fan_off_thresholds])
        hysteresis = avg_on - avg_off
        print(f"\n  RECOMMENDED ESP8266 SETTINGS:")
        print(f"    Fan ON  threshold: {avg_on:.0f}%")
        print(f"    Fan OFF threshold: {avg_off:.0f}%")
        print(f"    Hysteresis band:   {hysteresis:.0f}%")
        print(f"\n  (This means: turn fan ON at {avg_on:.0f}%, keep running until")
        print(f"   humidity drops to {avg_off:.0f}%, then turn OFF)")


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Smart Silo RL Fan Optimization")
    parser.add_argument("--data", type=str, default=None, help="Path to CSV data file")
    parser.add_argument("--timesteps", type=int, default=RL_TOTAL_TIMESTEPS,
                        help=f"Training timesteps (default: {RL_TOTAL_TIMESTEPS})")
    parser.add_argument("--evaluate-only", action="store_true",
                        help="Skip training, load saved model")
    args = parser.parse_args()
    
    # Load data
    data_path = args.data or os.path.join(DATA_DIR, "silo_data_latest.csv")
    if os.path.exists(data_path):
        df = pd.read_csv(data_path, parse_dates=["timestamp"])
        df = df.dropna(subset=["humidity", "temperature"]).reset_index(drop=True)
        print(f"[+] Loaded {len(df)} rows for environment simulation")
    else:
        print("[!] No data file found. Using synthetic environment data.")
        df = None
    
    # Create environment
    env = GrainSiloEnv(data=df)
    
    model_path = os.path.join(MODEL_DIR, "ppo_fan_controller")
    
    if args.evaluate_only:
        if not os.path.exists(model_path + ".zip"):
            print(f"[!] No saved model at {model_path}.zip — train first!")
            sys.exit(1)
        model = PPO.load(model_path, env=env)
        print("[+] Loaded saved model.")
    else:
        print(f"\n{'='*60}")
        print(f"  TRAINING PPO AGENT ({args.timesteps:,} timesteps)")
        print(f"{'='*60}")
        
        model = PPO(
            "MlpPolicy",
            env,
            verbose=1,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            tensorboard_log=os.path.join(MODEL_DIR, "tb_logs"),
        )
        
        model.learn(total_timesteps=args.timesteps, progress_bar=True)
        model.save(model_path)
        print(f"  [+] Model saved: {model_path}.zip")
    
    # ── Evaluate: Threshold Baseline vs RL Agent ──
    print(f"\n{'='*60}")
    print("  EVALUATION: Threshold vs RL Agent")
    print(f"{'='*60}")
    
    eval_env = GrainSiloEnv(data=df)
    
    baseline_result = run_threshold_baseline(GrainSiloEnv(data=df))
    rl_result = run_rl_agent(GrainSiloEnv(data=df), model)
    
    b_reward, _, _, b_metrics = baseline_result
    r_reward, _, _, r_metrics = rl_result
    
    print(f"\n  Threshold Baseline:")
    print(f"    Reward: {b_reward:.1f} | Fan duty: {b_metrics['fan_duty_cycle']:.1%} | Toggles: {b_metrics['total_toggles']}")
    print(f"\n  RL Agent:")
    print(f"    Reward: {r_reward:.1f} | Fan duty: {r_metrics['fan_duty_cycle']:.1%} | Toggles: {r_metrics['total_toggles']}")
    
    energy_saving = max(0, (1 - r_metrics["fan_duty_cycle"] / max(b_metrics["fan_duty_cycle"], 0.001))) * 100
    print(f"\n  💡 Energy Savings: {energy_saving:.1f}%")
    
    # Visualize
    plot_comparison(baseline_result, rl_result)
    
    # Extract interpretable rules
    extract_policy_rules(eval_env, model)
    
    print(f"\n{'='*60}")
    print("  FAN OPTIMIZATION COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

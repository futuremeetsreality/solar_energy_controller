# File: custom_components/solar_energy_controller/coordinator.py
# Timestamp: 2026-08-10 23:30 CEST

from __future__ import annotations
from datetime import datetime, timedelta
import logging
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from .const import *
from .decision_log import append_decision_log, format_decision
from .price_parser import future_prices
_LOGGER = logging.getLogger(__name__)

class SolarEnergyControllerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Economic shadow controller. 0.1.x never writes to devices."""
    def __init__(self,hass:HomeAssistant,entry:ConfigEntry)->None:
        self.entry=entry; self.cfg={**DEFAULTS,**entry.data,**entry.options}
        super().__init__(hass,_LOGGER,name=DOMAIN,update_interval=timedelta(minutes=int(self.cfg[CONF_INTERVAL_MIN])))
        self._store=Store(hass,STORAGE_VERSION,f"{STORAGE_KEY}_{entry.entry_id}"); self._loaded=False
        self.simulation_enabled=True; self.virtual_energy_kwh=None; self.miner_simulated_on=False; self.miner_locked_until=None
        self.accumulation_date=dt_util.now().date().isoformat(); self.accumulation_start=dt_util.now().isoformat(); self.last_update=None
        self.last_actual_export_energy=None; self.last_actual_import_energy=None; self.metrics=self._fresh_metrics(); self.decision_log=[]
    @staticmethod
    def _fresh_metrics():
        return {k:0.0 for k in ("sim_export_kwh","sim_export_revenue_eur","sim_import_kwh","sim_import_cost_eur","sim_self_supply_kwh","sim_self_supply_value_eur","sim_miner_hours","sim_doge","sim_mining_value_eur","actual_export_revenue_eur","actual_import_cost_eur","actual_self_supply_value_eur","actual_miner_hours","actual_doge","actual_mining_value_eur")}
    async def _async_load(self):
        if self._loaded:return
        s=await self._store.async_load() or {}; self.simulation_enabled=bool(s.get("simulation_enabled",True)); self.virtual_energy_kwh=s.get("virtual_energy_kwh"); self.miner_simulated_on=bool(s.get("miner_simulated_on",False))
        x=s.get("miner_locked_until"); self.miner_locked_until=dt_util.parse_datetime(x) if x else None; self.accumulation_date=s.get("accumulation_date",self.accumulation_date); self.accumulation_start=s.get("accumulation_start",self.accumulation_start); self.metrics.update(s.get("metrics",{})); self.decision_log=list(s.get("decision_log",[]))[-192:]; self._loaded=True
    async def async_set_simulation_enabled(self,enabled): self.simulation_enabled=enabled; await self._async_save(); await self.async_request_refresh()
    async def _async_save(self): await self._store.async_save({"simulation_enabled":self.simulation_enabled,"virtual_energy_kwh":self.virtual_energy_kwh,"miner_simulated_on":self.miner_simulated_on,"miner_locked_until":self.miner_locked_until.isoformat() if self.miner_locked_until else None,"accumulation_date":self.accumulation_date,"accumulation_start":self.accumulation_start,"metrics":self.metrics,"decision_log":self.decision_log})
    def _state_float(self,e):
        if not e:return None
        s=self.hass.states.get(e)
        if s is None or s.state in ("unknown","unavailable","none",""):return None
        try:return float(s.state)
        except (TypeError,ValueError):return None
    def _power_kw(self,e):
        v=self._state_float(e)
        if v is None:return 0.0
        s=self.hass.states.get(e); u=str(s.attributes.get("unit_of_measurement","W")) if s else "W"; return max(0.0,v if u.lower()=="kw" else v/1000)
    def _energy_kwh(self,e):
        v=self._state_float(e)
        if v is None:return None
        s=self.hass.states.get(e); u=str(s.attributes.get("unit_of_measurement","kWh")) if s else "kWh"; return v/1000 if u.lower()=="wh" else v
    def _price_ct(self,e):
        v=self._state_float(e)
        if v is None:return None
        s=self.hass.states.get(e); u=str(s.attributes.get("unit_of_measurement","ct/kWh")) if s else "ct/kWh"; q=u.lower().replace(" ",""); return v*100 if "€/kwh" in q or "eur/kwh" in q else v
    def _sum_energy(self,*entities): return sum(v for v in (self._energy_kwh(e) for e in entities) if v is not None)
    def _timestamp(self,e):
        s=self.hass.states.get(e) if e else None
        if not s:return None
        d=dt_util.parse_datetime(s.state); return dt_util.as_local(d) if d else None
    def _forecast(self): return {"today":self._sum_energy(self.cfg[CONF_FORECAST_TODAY_1],self.cfg[CONF_FORECAST_TODAY_2]),"remaining":self._sum_energy(self.cfg[CONF_FORECAST_REMAINING_1],self.cfg[CONF_FORECAST_REMAINING_2]),"tomorrow":self._sum_energy(self.cfg[CONF_FORECAST_TOMORROW_1],self.cfg[CONF_FORECAST_TOMORROW_2]),"next_hour":self._sum_energy(self.cfg[CONF_FORECAST_NEXT_HOUR_1],self.cfg[CONF_FORECAST_NEXT_HOUR_2]),"peak_tomorrow":self._timestamp(self.cfg[CONF_FORECAST_PEAK_TOMORROW_1]) or self._timestamp(self.cfg[CONF_FORECAST_PEAK_TOMORROW_2])}
    def _actual_miner_on(self):
        s=self.hass.states.get(self.cfg[CONF_MINER_SWITCH]) if self.cfg[CONF_MINER_SWITCH] else None; return bool(s and s.state=="on")
    def _current_export_price_ct(self):
        v=self._price_ct(self.cfg[CONF_EFFECTIVE_EXPORT_PRICE]); return v if v is not None else (self._price_ct(self.cfg[CONF_EPEX_PRICE]) or 0.0)
    def _current_import_price_eur(self):
        v=self._price_ct(self.cfg[CONF_IMPORT_TOTAL_PRICE]) if self.cfg[CONF_IMPORT_TOTAL_PRICE] else None; return v/100 if v is not None else float(self.cfg[CONF_IMPORT_FALLBACK_EUR_KWH])
    def _miner_break_even_ct(self): return (float(self.cfg[CONF_DOGE_PER_DAY])/24*float(self.cfg[CONF_DOGE_TARGET_EUR]))/max(.001,float(self.cfg[CONF_MINER_NOMINAL_POWER_KW]))*100
    def _future_price_stats(self,now):
        s=self.hass.states.get(self.cfg[CONF_EPEX_PRICE]); series=future_prices(s.attributes,now,int(self.cfg[CONF_HORIZON_H])) if s else []; vals=[p for _,p in series]
        if not vals:return [],None,None,None
        o=sorted(vals); return series,min(vals),max(vals),o[max(0,int(len(o)*.25)-1)]
    def _target_soc(self,current,series,forecast):
        minimum=float(self.cfg[CONF_BATTERY_MIN_SOC]); tomorrow=forecast["tomorrow"]; remaining=forecast["remaining"]
        if not series:return minimum,"No future EPEX series; minimum reserve."
        prices=sorted(p for _,p in series); p25=prices[int((len(prices)-1)*.25)]; p50=prices[int((len(prices)-1)*.5)]; p75=prices[int((len(prices)-1)*.75)]; peak=max(prices); spread=peak-current
        if current<=p25 and spread>=5: base=95; why="current price is in the cheapest quartile"
        elif current<=p50 and spread>=3: base=75; why="current price is below the future median"
        elif current<p75 and spread>=1.5: base=55; why="current price is moderately cheap"
        else: base=minimum; why="current price offers no strong storage advantage"
        if tomorrow<=25: pv_adj=20; pvwhy=f"weak tomorrow forecast ({tomorrow:.1f} kWh)"
        elif tomorrow<=45: pv_adj=10; pvwhy=f"moderate tomorrow forecast ({tomorrow:.1f} kWh)"
        elif tomorrow>=75: pv_adj=-20; pvwhy=f"strong tomorrow forecast ({tomorrow:.1f} kWh)"
        elif tomorrow>=55: pv_adj=-10; pvwhy=f"good tomorrow forecast ({tomorrow:.1f} kWh)"
        else: pv_adj=0; pvwhy=f"neutral tomorrow forecast ({tomorrow:.1f} kWh)"
        if remaining>=15: pv_adj-=10; pvwhy+=f", plus {remaining:.1f} kWh remaining today"
        target=max(minimum,min(95.0,base+pv_adj)); return target,f"{why}; {pvwhy}. Future peak {peak:.2f} ct/kWh."
    def _miner_should_start(self,now,price,surplus,series):
        be=self._miner_break_even_ct(); nominal=float(self.cfg[CONF_MINER_NOMINAL_POWER_KW])
        if price>=be or surplus<nominal:return False
        end=now+timedelta(minutes=int(self.cfg[CONF_MINER_MIN_RUNTIME_MIN])); window=[p for d,p in series if now<=d<end]; return not window or max(window)<be
    def _reset_if_new_day(self,now):
        t=now.date().isoformat()
        if t!=self.accumulation_date:self.accumulation_date=t;self.accumulation_start=now.isoformat();self.metrics=self._fresh_metrics();self.last_actual_export_energy=None;self.last_actual_import_energy=None
    async def _async_update_data(self):
        await self._async_load(); now=dt_util.now(); self._reset_if_new_day(now); cap=float(self.cfg[CONF_BATTERY_CAPACITY_KWH]); minsoc=float(self.cfg[CONF_BATTERY_MIN_SOC]); minenergy=cap*minsoc/100; actual_soc=self._state_float(self.cfg[CONF_BATTERY_SOC])
        if self.virtual_energy_kwh is None:self.virtual_energy_kwh=cap*max(minsoc,min(100,actual_soc if actual_soc is not None else minsoc))/100
        ih=float(self.cfg[CONF_INTERVAL_MIN])/60
        if self.last_update is not None:
            elapsed=(now-self.last_update).total_seconds()/3600
            if 0<elapsed<ih*2.5:ih=elapsed
        self.last_update=now; pv=self._power_kw(self.cfg[CONF_PV_POWER]); house=self._power_kw(self.cfg[CONF_HOUSE_LOAD]); actual_import=self._power_kw(self.cfg[CONF_GRID_IMPORT_POWER]); price=self._current_export_price_ct(); import_eur=self._current_import_price_eur(); series,fmin,fmax,low=self._future_price_stats(now); fc=self._forecast(); target,target_reason=self._target_soc(price,series,fc); target_energy=cap*target/100; surplus=max(0,pv-house)
        locked=bool(self.miner_locked_until and now<self.miner_locked_until)
        if self.simulation_enabled:
            if locked:self.miner_simulated_on=True
            elif self._miner_should_start(now,price,surplus,series):self.miner_simulated_on=True;self.miner_locked_until=now+timedelta(minutes=int(self.cfg[CONF_MINER_MIN_RUNTIME_MIN]))
            else:self.miner_simulated_on=False;self.miner_locked_until=None
        else:self.miner_simulated_on=False;self.miner_locked_until=None
        exp=imp=chg=dis=selfsup=0.0; miner=float(self.cfg[CONF_MINER_NOMINAL_POWER_KW]) if self.miner_simulated_on else 0
        if self.simulation_enabled:
            direct=min(pv,house);selfsup+=direct;deficit=max(0,house-pv)
            if deficit>0 and self.virtual_energy_kwh>minenergy:
                avail=min(float(self.cfg[CONF_BATTERY_MAX_DISCHARGE_KW]),(self.virtual_energy_kwh-minenergy)*float(self.cfg[CONF_BATTERY_DISCHARGE_EFFICIENCY])/max(ih,.001));dis=min(deficit,avail);deficit-=dis;selfsup+=dis;self.virtual_energy_kwh-=dis*ih/float(self.cfg[CONF_BATTERY_DISCHARGE_EFFICIENCY])
            imp+=deficit; rem=max(0,pv-house); minerpv=min(rem,miner);rem-=minerpv;imp+=max(0,miner-minerpv)
            if self.virtual_energy_kwh<target_energy and rem>0 and self.virtual_energy_kwh<cap:
                maxcap=(cap-self.virtual_energy_kwh)/max(ih,.001)/float(self.cfg[CONF_BATTERY_CHARGE_EFFICIENCY]);chg=min(rem,float(self.cfg[CONF_BATTERY_MAX_CHARGE_KW]),maxcap);self.virtual_energy_kwh+=chg*ih*float(self.cfg[CONF_BATTERY_CHARGE_EFFICIENCY]);rem-=chg
            exp=max(0,rem);self.virtual_energy_kwh=min(cap,max(minenergy,self.virtual_energy_kwh));self.metrics["sim_export_kwh"]+=exp*ih;self.metrics["sim_export_revenue_eur"]+=exp*ih*price/100;self.metrics["sim_import_kwh"]+=imp*ih;self.metrics["sim_import_cost_eur"]+=imp*ih*import_eur;self.metrics["sim_self_supply_kwh"]+=selfsup*ih;self.metrics["sim_self_supply_value_eur"]+=selfsup*ih*import_eur
            if self.miner_simulated_on:
                doge=float(self.cfg[CONF_DOGE_PER_DAY])/24*ih;self.metrics["sim_miner_hours"]+=ih;self.metrics["sim_doge"]+=doge;self.metrics["sim_mining_value_eur"]+=doge*float(self.cfg[CONF_DOGE_TARGET_EUR])
            self.metrics["actual_self_supply_value_eur"]+=max(0,house-actual_import)*ih*import_eur
            if self._actual_miner_on():
                doge=float(self.cfg[CONF_DOGE_PER_DAY])/24*ih;self.metrics["actual_miner_hours"]+=ih;self.metrics["actual_doge"]+=doge;self.metrics["actual_mining_value_eur"]+=doge*float(self.cfg[CONF_DOGE_TARGET_EUR])
            ae=self._energy_kwh(self.cfg[CONF_GRID_EXPORT_ENERGY_TODAY]); ai=self._energy_kwh(self.cfg[CONF_GRID_IMPORT_ENERGY_TODAY])
            if ae is not None and self.last_actual_export_energy is not None:self.metrics["actual_export_revenue_eur"]+=max(0,ae-self.last_actual_export_energy)*price/100
            if ai is not None and self.last_actual_import_energy is not None:self.metrics["actual_import_cost_eur"]+=max(0,ai-self.last_actual_import_energy)*import_eur
            self.last_actual_export_energy=ae;self.last_actual_import_energy=ai
        sim=self.metrics["sim_export_revenue_eur"]+self.metrics["sim_self_supply_value_eur"]+self.metrics["sim_mining_value_eur"]-self.metrics["sim_import_cost_eur"]; actual=self.metrics["actual_export_revenue_eur"]+self.metrics["actual_self_supply_value_eur"]+self.metrics["actual_mining_value_eur"]-self.metrics["actual_import_cost_eur"]
        rec="PAUSED";reason="Simulation is off; no live control exists."
        if self.simulation_enabled:
            if self.miner_simulated_on:rec="MINING_PRIORITY";reason=f"Mining value {self._miner_break_even_ct():.2f} ct/kWh exceeds export {price:.2f} ct/kWh."
            elif self.virtual_energy_kwh<target_energy and surplus>0:rec="CHARGE_PRIORITY";reason=f"Target SOC {target:.0f}%. {target_reason}"
            elif surplus>0:rec="EXPORT_PRIORITY";reason=f"Reserve satisfied. {target_reason}"
            else:rec="HOUSE_RESERVE";reason=f"No PV surplus; battery may serve house load down to {minsoc:.0f}%. {target_reason}"
        log_entry={"timestamp":now.isoformat(),"time_local":now.strftime("%H:%M"),"recommendation":rec,"reason":reason,"pv_kw":round(pv,3),"house_kw":round(house,3),"actual_soc":None if actual_soc is None else round(actual_soc,1),"virtual_soc":round(self.virtual_energy_kwh/cap*100,1),"target_soc":round(target,1),"export_price_ct":round(price,3),"import_price_eur":round(import_eur,4),"future_min_ct":fmin,"future_max_ct":fmax,"forecast_remaining_kwh":round(fc["remaining"],2),"forecast_tomorrow_kwh":round(fc["tomorrow"],2),"miner_on":self.miner_simulated_on,"miner_locked_until":self.miner_locked_until.isoformat() if self.miner_locked_until else None,"sim_export_kw":round(exp,3),"sim_import_kw":round(imp,3),"sim_battery_charge_kw":round(chg,3),"sim_battery_discharge_kw":round(dis,3),"simulated_net_benefit_eur":round(sim,3),"observed_net_benefit_eur":round(actual,3),"advantage_eur":round(sim-actual,3)}
        self.decision_log=append_decision_log(self.decision_log,log_entry)
        data={**self.metrics,"simulation_enabled":self.simulation_enabled,"recommendation":rec,"reason":reason,"target_reason":target_reason,"virtual_soc":self.virtual_energy_kwh/cap*100,"target_soc":target,"actual_soc":actual_soc,"pv_kw":pv,"house_kw":house,"sim_export_kw":exp,"sim_import_kw":imp,"sim_battery_charge_kw":chg,"sim_battery_discharge_kw":dis,"miner_simulated_on":self.miner_simulated_on,"miner_locked_until":self.miner_locked_until.isoformat() if self.miner_locked_until else None,"miner_break_even_ct":self._miner_break_even_ct(),"export_price_ct":price,"import_price_eur":import_eur,"future_price_points":len(series),"future_min_ct":fmin,"future_max_ct":fmax,"low_quartile_ct":low,"forecast_today_kwh":fc["today"],"forecast_remaining_today_kwh":fc["remaining"],"forecast_tomorrow_kwh":fc["tomorrow"],"forecast_next_hour_kwh":fc["next_hour"],"forecast_peak_tomorrow":fc["peak_tomorrow"].isoformat() if fc["peak_tomorrow"] else None,"simulated_benefit_eur":sim,"actual_benefit_eur":actual,"advantage_eur":sim-actual,"accumulation_start":self.accumulation_start,"last_decision":format_decision(log_entry),"decision_log":self.decision_log,"decision_log_count":len(self.decision_log)};await self._async_save();return data

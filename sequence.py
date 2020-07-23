import copy
import numpy as np
import matplotlib.pyplot as plt
from instruction.trigger import Trigger
from util.topological_sort import weighted_topological_sort

plt.rcParams['ytick.minor.visible'] = False
plt.rcParams['xtick.top']           = True
plt.rcParams['ytick.right']         = True
plt.rcParams['ytick.minor.visible'] = False
plt.rcParams['xtick.direction']     = 'in'
plt.rcParams['ytick.direction']     = 'in'
plt.rcParams['font.family']         = 'arial'
plt.rcParams["mathtext.fontset"]    = 'stixsans'
plt.rcParams['xtick.major.width']   = 0.5
plt.rcParams['ytick.major.width']   = 0.5
plt.rcParams['font.size']           = 16
plt.rcParams['axes.linewidth']      = 1.0

class Sequence:
    """Pulse sequence management class for timedomain measurement"""

    def __init__(self):
        """Initialize the internal setting
        """
        self._reset()

    def __repr__(self):
        lineA = 6
        lineB = 70
        lineC = 40
        lineD = 20
        lineE = lineB + lineC - lineD - 4
        print_str = f"Sequence Instruction List\n"
        print_str += "  ID".ljust(lineA) + "|".center(4)
        print_str += "Instruction Name".ljust(lineB) + "|".center(4)
        print_str += "Target Port".ljust(lineC)
        print_str += "\n"
        for index, (instruction, port) in enumerate(self.instruction_list):
            print_str += "-"*(lineA + lineB + lineC + 4) + "\n"
            print_str += f"  {index}".ljust(lineA) + "|".center(4)
            print_str += f"{instruction.name}".ljust(lineB) + "|".center(4)
            print_str += f"{port}".ljust(lineC)
            print_str += "\n"
            print_str += "-"*(lineA + lineB + lineC + 4) + "\n"
            for key, value in instruction.input_params.items():
                    print_str += "".ljust(lineA) + "|".center(4)
                    print_str += f"     {key}".ljust(lineD)
                    print_str += ":".center(4)
                    print_str += f"{value}"[:lineE].ljust(lineE)
                    print_str += "\n"
        print_str += "-"*(lineA + lineB + lineC + 4) + "\n"
        return print_str

    def _reset(self):
        self.port_list = []
        self.instruction_list = []
        self.trigger_index = 0
        self.trigger_position_list = None
        self.max_waveform_lenght = None

    def _verify_port(self, port):
        """Add new Port into the port_list
        Args:
            port (Port): control port for qubit drive, cavity drive, cross resonance, or impa pump
        """
        for tmp in self.port_list:
            if port.name == tmp.name:
                return tmp
        new_port = copy.deepcopy(port)
        new_port._reset()
        self.port_list.append(new_port)
        return new_port

    def add(self, instruction, port):
        """Add Instruction into the instruction_list
        Args:
            instruction (Instruction): Pulse, Command, or Trigger
            port (Port): control port for qubit drive, cavity drive, cross resonance, or impa pump
        """
        port = self._verify_port(port)
        self.instruction_list.append((copy.deepcopy(instruction), port))

    def trigger(self, port_list, align="left"):
        """Add Trigger into the instruction_list
        Args:
            port_list (list): list of the target ports to be syncronized
            align (str): indicate align mode in the next trigger-edge ("left", "middle", and "right")
        """
        port_list = [self._verify_port(port) for port in port_list]
        self.instruction_list.append((Trigger(align=align), port_list))

    # def align(self, port, align):
    #     return AlignManager(self, port, align)

    def call(self, sequence):
        """Combine the instruction_list with the other sequence
        Args:
            sequence (Sequence): sequence
        """
        for instruction, port in sequence.instruction_list:
            self.add(instruction, port)

    def compile(self):
        """Compile the instructions

        """
        ## set trigger index
        self.instruction_list.insert(0, (Trigger(), self.port_list)) # start trigger (phase zero point)
        self.instruction_list.append((Trigger(), self.port_list)) # end trigger
        for instruction, port in self.instruction_list:
            if instruction.type is "Trigger":
                instruction.trigger_index = self.trigger_index
                self.trigger_index += 1
                for tmp_port in port:
                    tmp_port._add(instruction)
            else:
                port._add(instruction)

        ## generate dag
        node_list = list(range(self.trigger_index))
        weighted_edge_list = []
        for port in self.port_list:
            weighted_edge_list += port._get_trigger_edge_list()

        ## weighted topological sort
        self.trigger_position_list = weighted_topological_sort(node_list, weighted_edge_list)

        ## syncronize trigger_position
        for port in self.port_list:
            port._sync_trigger_position(self.trigger_position_list)

        ## execute instructions
        waveform_length = []
        for port in self.port_list:
            port._execute_instructions()
            waveform_length.append(port.position)
        self.max_waveform_lenght = max(waveform_length)

        ## write waveform
        for port in self.port_list:
            port._write_waveform(self.max_waveform_lenght)

    def plot_waveform(self, port_name_list=None, time_range=None, cancell_sideband=True):
        """plot waveform saved in the Ports
        Args:
            port_name_list (list): List of the port_name to plot waveform
            time_range (tupple): time_range for plot written as (start, end)
            cancell_sideband (bool): bool index to identify whether cancell or not the waveform charping for plot
        """

        if port_name_list is None:
            plot_port_list = self.port_list
        else:
            plot_port_list = []
            for port in self.port_list:
                if port.name in port_name_list:
                    plot_port_list.append(port)

        if time_range is None:
            plot_time_range = (0, self.max_waveform_lenght)
        else:
            plot_time_range = time_range

        plt.figure(figsize=(20,1.5*len(plot_port_list)))
        for i, port in enumerate(plot_port_list):
            plt.subplot(len(plot_port_list), 1, i+1)
            plt.axhline(0, color="black", linestyle="-")
            for measurement_window in port.measurement_window_list:
                plt.axvspan(measurement_window[0], measurement_window[1], color="green", alpha=0.3)
            if cancell_sideband:
                plot_waveform = np.exp(-1j*(2*np.pi*port.SIDEBAND_FREQ*port.time))*port.waveform
            else:
                plot_waveform = port.waveform
            plt.step(port.time, plot_waveform.real)
            plt.step(port.time, plot_waveform.imag)
            plt.fill_between(port.time, plot_waveform.real, step="pre", alpha=0.4)
            plt.fill_between(port.time, plot_waveform.imag, step="pre", alpha=0.4)
            for trigger_index, _ in port.trigger_node_list:
                position = self.trigger_position_list[trigger_index]
                plt.axvline(position, color="red", linestyle="--")
                if plot_time_range[0] <= position <= plot_time_range[1]:
                    plt.text(x=position, y=-1, s=trigger_index, color="red", fontsize=12)
            plt.text(x=plot_time_range[0], y=-0, s=port.name,fontsize=18)
            plt.ylim(-1,1)
            plt.xlim(plot_time_range[0], plot_time_range[1])
            plt.grid()
            plt.ylabel("Amplitude")
            plt.tick_params(labelbottom=False)
        plt.tight_layout()
        plt.tick_params(labelbottom=True)
        plt.xlabel("Time (ns)")
        plt.show()

    def get_waveform_information(self):
        """get waveform information for I/O with measurement_tools
        """
        waveform_information = {}
        for port in self.port_list:
            waveform_information[port.name] = {
                "daq_length" : port.position,
                "measurement_window" : port.measurement_window_list,
                "waveform" : port.waveform,
                "waveform_updated" : False,
            }
        return waveform_information

    def dump_setting(self):
        """Dump all settings as Dictionary
        
        Returns:
            setting (dict): setting file of the Sequence
        """
        from instruction.instruction_parser import generate_setting_from_instruction

        setting = []
        for instruction, port in self.instruction_list:
            inst_setting = generate_setting_from_instruction(instruction)
            if instruction.type == "Trigger":
                port_setting = [tmp_port.name for tmp_port in port]
            else:
                port_setting = port.name
            setting.append(
                {
                    "instruction" : inst_setting,
                    "port" : port_setting
                }
            )
        return setting

    def load_setting(self, setting):
        """Load settings from Dictionary
        
        """
        from port import Port
        from instruction.instruction_parser import generate_instruction_from_setting

        self._reset()
        for tmp_setting in setting:
            inst_setting = tmp_setting["instruction"]
            port_setting = tmp_setting["port"]

            instruction = generate_instruction_from_setting(inst_setting)
            if instruction.type == "Trigger":
                port = [Port(name=port_name) for port_name in port_setting]
            else:
                port = Port(name=port_setting)

            self.add(instruction, port)
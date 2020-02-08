package main

import (
	"errors"
	"flag"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

var description = `
Rotate MAC addresses on a specified interval, with a bit of variation added.
Requires superuser privileges. Supports macOS and Linux.`

const (
	defaultDeviceName = "eth0"
	defaultCycleSecs  = 30 * 60
)

const (
	cycleVariance = .25
	maxErrs       = 3
)

type vendor string

const (
	vendorIntel          vendor = "Intel"
	vendorHewlettPackard        = "HP"
	vendorFoxconn               = "Foxconn"
	vendorCisco                 = "Cisco"
	vendorAmd                   = "AMD"
)

type macAddr string

const (
	macAddrIntel          macAddr = "00:1b:77"
	macAddrHewlettPackard         = "00:1b:78"
	macAddrFoxconn                = "00:01:6c"
	macAddrCisco                  = "00:10:29"
	macAddrAmd                    = "00:0c:87"
)

type vendorMac struct {
	vendor vendor
	mac    macAddr
}

var vendors = []vendorMac{
	{vendorIntel, macAddrIntel},
	{vendorHewlettPackard, macAddrHewlettPackard},
	{vendorFoxconn, macAddrFoxconn},
	{vendorCisco, macAddrCisco},
	{vendorAmd, macAddrAmd},
}

func pickVendor() (vendor, macAddr) {
	n := rand.Intn(len(vendors))
	vendorMac := vendors[n]
	return vendorMac.vendor, vendorMac.mac
}

type newSetMacCmd func(devName string, mac macAddr) (string, []string)

func newSetMacUnixCmd(devName string, mac macAddr) (string, []string) {
	cmd := "ifconfig"
	args := []string{devName, "ether", string(mac)}
	return cmd, args
}

func newSetMacLinuxCmd(devName string, mac macAddr) (string, []string) {
	cmd := "ip"
	args := []string{"link", "set", "dev", devName, "addr", string(mac)}
	return cmd, args
}

func newRandomMac() (vendor, macAddr) {
	var fragments [4]string

	vendor, addr := pickVendor()
	fragments[0] = string(addr)

	for i := 1; i < 4; i++ {
		fragments[i] = fmt.Sprintf(
			"%d%d",
			rand.Intn(9),
			rand.Intn(9),
		)
	}

	mac := strings.Join(fragments[:], ":")
	return vendor, macAddr(mac)
}

func variate(seconds uint, variance float64) float64 {
	delta := (rand.Float64() - .5) * variance
	return float64(seconds) + (float64(seconds) * delta)
}

type macChange interface {
	handle(errs []error) []error
}

type successfulMacChange struct {
	vendor vendor
	mac    macAddr
}

func (change *successfulMacChange) handle([]error) []error {
	log.Printf(
		"set to MAC address %s of vendor %s\n",
		string(change.mac),
		string(change.vendor),
	)
	return nil
}

type failedMacChange struct {
	err error
}

func (change failedMacChange) handle(errs []error) []error {
	remaining := maxErrs - len(errs)
	log.Printf("an error occured: %s", change.err)
	log.Printf(
		"the program wills top if %d more occur sequentially\n",
		remaining,
	)
	return append(errs, error(change.err))
}

func isLinux() bool {
	return runtime.GOOS == "linux"
}

func setMac(deviceName string, newSetMacCmd newSetMacCmd, dryRun bool) macChange {
	vendor, addr := newRandomMac()
	prog, args := newSetMacCmd(deviceName, addr)

	if dryRun {
		argsStr := strings.Join(args, " ")
		log.Printf("would run `%s %s`\n", prog, argsStr)
	} else {
		cmd := exec.Command(prog, args...)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err := cmd.Run(); err != nil {
			return &failedMacChange{err}
		}
	}
	return &successfulMacChange{vendor, addr}
}

func newMacChangeErr(errs []error) error {
	msgs := make([]string, len(errs))
	for i, err := range errs {
		msgs[i] = err.Error()
	}

	errMsg := strings.Join(msgs, "\n")
	return errors.New("too many MAC change errors occured:\n" + errMsg)
}

func rotateMacAddrs(deviceName string, cycleSecs uint, newSetMacCmd newSetMacCmd, dryRun bool) error {
	var errs []error

	for {
		change := setMac(deviceName, newSetMacCmd, dryRun)

		errs = change.handle(errs)
		if maxErrs <= len(errs) {
			return newMacChangeErr(errs)
		}

		variation := variate(cycleSecs, cycleVariance)
		duration := time.Second * time.Duration(math.Round(variation))
		log.Printf(
			"waiting for %d seconds until next rotation\n",
			duration/time.Second,
		)
		time.Sleep(duration)
	}
}

func initUsage() {
	defaultUsage := flag.Usage

	flag.Usage = func() {
		defaultUsage()
		fmt.Println(description)
	}
}

type flags struct {
	deviceName string
	cycleSecs  uint
	dryRun     bool
}

func parseFlags() flags {
	var deviceName string
	var cycleSecs uint
	var dryRun bool

	flag.StringVar(
		&deviceName,
		"device-name",
		defaultDeviceName,
		"the network device name",
	)
	flag.UintVar(
		&cycleSecs,
		"cycle-secs",
		defaultCycleSecs,
		"the seconds between each rotation (with variance)",
	)
	flag.BoolVar(
		&dryRun,
		"dry-run",
		false,
		"display the commands to be run without running them",
	)

	flag.Parse()
	return flags{deviceName, cycleSecs, dryRun}
}

func main() {
	initUsage()
	flags := parseFlags()

	var newSetMacCmd newSetMacCmd
	if isLinux() {
		newSetMacCmd = newSetMacLinuxCmd
	} else {
		newSetMacCmd = newSetMacUnixCmd
	}

	log.Println("rotating MAC address...")
	err := rotateMacAddrs(
		flags.deviceName,
		flags.cycleSecs,
		newSetMacCmd,
		flags.dryRun,
	)
	if err != nil {
		log.Fatalln(err)
	}
}

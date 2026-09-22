/// Monedero: saldo, oro de por vida y el historial de movimientos.
///
/// `GET /wallet` estaba entero del lado servidor —saldo, ganado y gastado de
/// por vida, movimientos paginados— y el cliente hasta tenía `Monedero`,
/// `RepoTienda.monedero()` y un método de controlador con manejo de error
/// propio ya escritos. Faltaba exactamente una cosa: la pantalla que lo
/// pidiera. El oro solo se veía como un número suelto en la cabecera del
/// héroe, el mercado, la hoja de un ítem y las piezas del personaje — nunca
/// el total ganado, el total gastado, ni de dónde salió cada movimiento.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/personaje.dart';
import '../inicio/widgets/esqueletos.dart';
import 'widgets/piezas.dart';

/// Detalle del monedero (saldo, totales de por vida e historial).
class PantallaMonedero extends StatefulWidget {
  const PantallaMonedero({super.key});

  @override
  State<PantallaMonedero> createState() => _PantallaMonederoState();
}

class _PantallaMonederoState extends State<PantallaMonedero> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorPersonaje>().cargarMonedero();
    });
  }

  @override
  Widget build(BuildContext context) {
    final ControladorPersonaje control = context.watch<ControladorPersonaje>();
    final Monedero? monedero = control.monedero;
    final bool cargaInicial = control.cargandoMonedero && monedero == null;

    return PantallaAtenea(
      titulo: 'Monedero',
      mostrarVolver: true,
      cuerpo: RefreshIndicator(
        onRefresh: () => control.cargarMonedero(forzar: true),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(top: Espacio.xs, bottom: Espacio.xxl),
          children: <Widget>[
            if (cargaInicial)
              const ListaEsqueleto(filas: 4, lineas: 2)
            else if (control.errorMonedero != null && monedero == null)
              Padding(
                padding: const EdgeInsets.only(top: Espacio.xl),
                child: EstadoError(
                  titulo: 'No pudimos traer tu monedero',
                  mensaje: control.errorMonedero!.mensaje,
                  alReintentar: () => control.cargarMonedero(forzar: true),
                ),
              )
            else if (monedero != null) ...<Widget>[
              _Totales(monedero: monedero),
              const SizedBox(height: Espacio.md),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Espacio.md),
                child: Text('Movimientos', style: context.textos.titleMedium),
              ),
              const SizedBox(height: Espacio.xs),
              if (monedero.movimientos.elementos.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: Espacio.md,
                    vertical: Espacio.md,
                  ),
                  child: EstadoVacio(
                    icono: Icons.receipt_long_rounded,
                    titulo: 'Todavía no hay movimientos',
                    mensaje:
                        'Cuando ganes o gastes oro, cada movimiento va a '
                        'quedar anotado aquí.',
                  ),
                )
              else ...<Widget>[
                for (final MovimientoOro m in monedero.movimientos.elementos)
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: Espacio.md,
                      vertical: Espacio.xxs,
                    ),
                    child: _FilaMovimiento(movimiento: m),
                  ),
                const SizedBox(height: Espacio.sm),
                _PiePagina(control: control),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

/// Saldo vigente y los dos totales de por vida.
class _Totales extends StatelessWidget {
  const _Totales({required this.monedero});

  final Monedero monedero;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Espacio.md),
      child: Row(
        children: <Widget>[
          Expanded(
            child: FichaEstadistica(
              icono: Icons.savings_rounded,
              color: p.oro,
              valor: cifra(monedero.saldo),
              etiqueta: 'Saldo',
            ),
          ),
          const SizedBox(width: Espacio.xs),
          Expanded(
            child: FichaEstadistica(
              icono: Icons.trending_up_rounded,
              color: p.exito,
              valor: cifra(monedero.totalGanado),
              etiqueta: 'Ganado en total',
            ),
          ),
          const SizedBox(width: Espacio.xs),
          Expanded(
            child: FichaEstadistica(
              icono: Icons.trending_down_rounded,
              color: p.textoSecundario,
              valor: cifra(monedero.totalGastado),
              etiqueta: 'Gastado en total',
            ),
          ),
        ],
      ),
    );
  }
}

/// Una fila del historial: motivo, fecha y el importe con su signo.
class _FilaMovimiento extends StatelessWidget {
  const _FilaMovimiento({required this.movimiento});

  final MovimientoOro movimiento;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool ingreso = movimiento.esIngreso;
    final Color color = ingreso ? p.exito : p.textoSecundario;
    final String signo = ingreso ? '+' : '−';

    return TarjetaAtenea(
      semantica:
          '${movimiento.motivoLegible}. ${ingreso ? 'Ganaste' : 'Gastaste'} '
          '${movimiento.cantidad} oro.',
      hijo: Row(
        children: <Widget>[
          Container(
            height: 36,
            width: 36,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.14),
              borderRadius: Redondeo.rChip,
            ),
            child: Icon(
              ingreso ? Icons.add_rounded : Icons.remove_rounded,
              size: 20,
              color: color,
            ),
          ),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(movimiento.motivoLegible, style: context.textos.bodyLarge),
                if (movimiento.ocurridoEn != null)
                  Text(
                    fechaCorta(movimiento.ocurridoEn!),
                    style: context.textos.bodySmall?.copyWith(
                      color: p.textoSecundario,
                    ),
                  ),
              ],
            ),
          ),
          Text(
            '$signo${movimiento.cantidad}',
            style: Cifras.pequena(context).copyWith(color: color),
          ),
        ],
      ),
    );
  }
}

/// Botón "Cargar más", su giro de espera, o el error de una página siguiente.
class _PiePagina extends StatelessWidget {
  const _PiePagina({required this.control});

  final ControladorPersonaje control;

  @override
  Widget build(BuildContext context) {
    if (control.cargandoMasMovimientos) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: Espacio.md),
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2.5),
          ),
        ),
      );
    }
    if (!control.hayMasMovimientos) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: Espacio.xs),
      child: Column(
        children: <Widget>[
          if (control.errorMonedero != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Espacio.xs),
              child: Text(
                control.errorMonedero!.mensaje,
                style: context.textos.bodySmall?.copyWith(
                  color: context.paleta.error,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          Center(
            child: TextButton.icon(
              onPressed: control.cargarMasMovimientos,
              icon: const Icon(Icons.expand_more_rounded),
              label: const Text('Cargar más'),
            ),
          ),
        ],
      ),
    );
  }
}

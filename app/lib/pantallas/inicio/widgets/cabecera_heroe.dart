/// Cabecera del Inicio (P04): quién eres y cómo vas.
///
/// Orden fijo del documento de UX: avatar, nivel y título de rango, barra de
/// XP hacia el siguiente nivel, y los medallones de racha y oro.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import 'avatar_heroe.dart';

/// Tarjeta del héroe: avatar, nivel, experiencia, racha y oro.
class CabeceraHeroe extends StatelessWidget {
  const CabeceraHeroe({
    required this.personaje,
    required this.racha,
    required this.saldoOro,
    super.key,
    this.capas = const <CapaAvatar>[],
    this.alTocarAvatar,
    this.alTocarRacha,
    this.alTocarOro,
  });

  /// Personaje con nivel, rango y progreso; nulo mientras no llega el panel.
  final Personaje? personaje;

  /// Racha vigente.
  final Racha racha;

  /// Saldo de oro.
  final int saldoOro;

  /// Capas del avatar que envía el panel.
  final List<CapaAvatar> capas;

  /// Lleva al Vestidor (P16).
  final VoidCallback? alTocarAvatar;

  /// Lleva a la Racha (P18).
  final VoidCallback? alTocarRacha;

  /// Lleva al Mercado (P15).
  final VoidCallback? alTocarOro;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Personaje? heroe = personaje;
    final int nivel = heroe?.nivel ?? 1;
    final String rango = heroe?.tituloRango ?? 'Aprendiz';
    final double avance = ((heroe?.porcentajeProgreso ?? 0) / 100).clamp(0, 1).toDouble();
    final int falta = heroe?.xpParaSiguiente ?? 0;

    return TarjetaAtenea(
      elevada: true,
      padding: const EdgeInsets.all(Espacio.md),
      hijo: Stack(
        children: <Widget>[
          Positioned(
            top: 0,
            left: 0,
            child: OrnamentoEsquina(color: p.oro.withValues(alpha: 0.45)),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: <Widget>[
                  AvatarHeroe(
                    arquetipo: heroe?.arquetipo ?? Arquetipo.acero,
                    capas: capas,
                    nombre: heroe?.nombre ?? '',
                    alTocar: alTocarAvatar,
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text('Nivel $nivel', style: Cifras.media(context)),
                        Text(
                          rango,
                          style: context.textos.bodyMedium?.copyWith(
                            color: p.textoSecundario,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(Medallon.nivel.icono, color: p.arcano, size: Tipo.titulo),
                ],
              ),
              const SizedBox(height: Espacio.md),
              Semantics(
                label: 'Experiencia hacia el nivel ${nivel + 1}',
                value: falta > 0 ? 'Faltan $falta puntos' : 'Nivel al máximo por hoy',
                child: ExcludeSemantics(
                  child: BarraProgreso(
                    valor: avance,
                    etiqueta: 'Experiencia',
                    color: p.oro,
                    textoDerecha: falta > 0
                        ? 'Faltan $falta XP'
                        : '${heroe?.xpTotal ?? 0} XP',
                  ),
                ),
              ),
              const SizedBox(height: Espacio.md),
              Row(
                children: <Widget>[
                  Expanded(
                    child: FichaMedallon(
                      tipo: Medallon.racha,
                      valor: racha.actual == 1 ? '1 día' : '${racha.actual} días',
                      etiqueta: _etiquetaRacha(racha),
                      alTocar: alTocarRacha,
                    ),
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: FichaMedallon(
                      tipo: Medallon.oro,
                      valor: '$saldoOro',
                      etiqueta: 'Oro',
                      alTocar: alTocarOro,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  static String _etiquetaRacha(Racha racha) {
    if (racha.actual == 0) return 'Racha por empezar';
    return racha.hoyCuenta ? 'Racha · hoy cuenta' : 'Racha · te toca hoy';
  }
}
